import asyncio
import math
import os
import json
import string
import random
import tempfile
import uuid
from typing import Optional

import pytest
import nacl.bindings
import nacl.utils
import nacl.secret

import sirius_sdk
from sirius_sdk.encryption import create_keypair, pack_message, unpack_message, bytes_to_b58, sign_message, \
    verify_signed_message, did_from_verkey, b58_to_bytes
from sirius_sdk.agent.aries_rfc.feature_0750_storage import *
from .helpers import calc_file_hash, calc_bytes_hash, calc_file_size, run_coroutines
from .conftest import get_pairwise3


def get_random_string(length):
    # choose from all lowercase letter
    letters = string.ascii_lowercase
    s = ''.join(random.choice(letters) for i in range(length))
    return s


class MockedReadOnlyStream(FileSystemReadOnlyStream):
    """Mocked stream to test retentions and other stream behaviour"""

    def __init__(self, path: str, chunks_num: int, enc: Optional[StreamDecryption] = None):
        super().__init__(path, chunks_num, enc)
        # Set if need to emulate read-ops delays
        self.retention_delay_sec: Optional[int] = None
        # Set to limit retention factor
        self.retention_delay_limit: Optional[int] = None
        self.__retention_delay_accum = 0

    async def read_chunk(self, no: int = None) -> (int, bytes):
        if self.retention_delay_sec:
            self.__retention_delay_accum += 1
            if self.retention_delay_limit is not None:
                if self.__retention_delay_accum >= self.retention_delay_limit:
                    allow_sleeping = False
                    self.__retention_delay_accum = 0
                else:
                    allow_sleeping = True
            else:
                allow_sleeping = True
            if allow_sleeping:
                await asyncio.sleep(self.retention_delay_sec)
        return await super().read_chunk(no)


@pytest.mark.asyncio
async def test_fs_streams(files_dir: str):
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)
    file_under_test_size = calc_file_size(file_under_test)
    # 1. Reading All Data
    for chunks_num in [10, 5, 1]:
        ro = FileSystemReadOnlyStream(file_under_test, chunks_num)
        await ro.open()
        try:
            read_data = await ro.read()
            read_data_md5 = calc_bytes_hash(read_data)
            assert read_data_md5 == file_under_test_md5
            assert ro.current_chunk == chunks_num
            assert await ro.eof() is True
        finally:
            await ro.close()
    # 2. Reading with chunks
    for chunks_num in [10, 5, 1]:
        ro = FileSystemReadOnlyStream(file_under_test, chunks_num)
        await ro.open()
        try:
            accum = b''
            async for chunk in ro.read_chunked():
                accum += chunk
            accum_md5 = calc_bytes_hash(read_data)
            assert accum_md5 == file_under_test_md5
            assert ro.current_chunk == chunks_num
            assert await ro.eof() is True
        finally:
            await ro.close()
    # 3. Write stream: create and write all data to file
    wo_file_path = os.path.join(files_dir, 'big_img_writeonly_stream.jpeg')
    for chunk_size in [100, 1024, 10000000]:
        wo = FileSystemWriteOnlyStream(wo_file_path, chunk_size)
        expected_chunks_num = math.ceil(file_under_test_size/chunk_size)
        await wo.create(truncate=True)
        try:
            with open(file_under_test, 'rb') as f:
                raw = f.read()
            await wo.open()
            try:
                assert wo.is_open is True
                await wo.write(raw)
                assert wo.chunks_num == expected_chunks_num
                assert wo.current_chunk == expected_chunks_num
            finally:
                await wo.close()
            wo_file_md5 = calc_file_hash(wo_file_path)
            assert wo_file_md5 == file_under_test_md5
        finally:
            os.remove(wo_file_path)


@pytest.mark.asyncio
async def test_fs_streams_seeks(files_dir: str):
    file_under_test = os.path.join(files_dir, 'seeks.bin')
    chunks = [b'chunk1', b'chunk2', b'chunk3']
    assert len(chunks[0]) == len(chunks[1]) == len(chunks[2])
    wo = FileSystemWriteOnlyStream(file_under_test, chunk_size=len(chunks[0]))
    await wo.create(truncate=True)
    try:
        await wo.open()
        try:
            # Check Writer
            assert wo.chunks_num == 0
            for no, chunk in enumerate(chunks):
                chunk_pos, writen = await wo.write_chunk(chunk, no)
                assert chunk_pos == no+1
                assert writen == len(chunk)
            assert wo.chunks_num == len(chunks)
            # Check Writer EOF
            with pytest.raises(StreamEOF):
                await wo.seek_to_chunk(1000)
            with pytest.raises(StreamEOF):
                await wo.write_chunk(b'', 1000)
            # Check Reader
            ro = FileSystemReadOnlyStream(file_under_test, chunks_num=len(chunks))
            await ro.open()
            try:
                assert ro.is_open is True
                assert ro.current_chunk == 0
                assert ro.chunks_num == len(chunks)
                for no, expected_chunk in enumerate(chunks):
                    await ro.seek_to_chunk(no)
                    chunk_offset, actual_chunk = await ro.read_chunk(no)
                    assert chunk_offset == no+1
                    assert expected_chunk == actual_chunk
                # Check Reader EOF
                assert await ro.eof() is True
                with pytest.raises(StreamEOF):
                    await ro.seek_to_chunk(1000)
                with pytest.raises(StreamEOF):
                    await ro.read_chunk()
            finally:
                await ro.close()
        finally:
            await wo.close()
    finally:
        os.remove(file_under_test)


@pytest.mark.asyncio
async def test_fs_streams_copy(files_dir: str):
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)
    file_under_test_size = calc_file_size(file_under_test)
    # 1. Reading All Data
    for chunk_size in [100, 1024, 10000000]:
        expected_chunks_num = math.ceil(file_under_test_size / chunk_size)
        ro = FileSystemReadOnlyStream(file_under_test, chunks_num=5)
        await ro.open()
        try:
            wo_file_path = os.path.join(files_dir, 'big_img_copy_stream.jpeg')
            try:
                wo = FileSystemWriteOnlyStream(wo_file_path, chunk_size)
                await wo.create(truncate=True)
                await wo.open()
                try:
                    await wo.copy(ro)
                finally:
                    await wo.close()
                with open(wo_file_path, 'rb') as f:
                    raw = f.read()
                copied_md5 = calc_bytes_hash(raw)
                assert copied_md5 == file_under_test_md5
                assert await ro.eof() is True
                assert wo.chunks_num == expected_chunks_num
            finally:
                os.remove(wo_file_path)
        finally:
            await ro.close()


@pytest.mark.asyncio
async def test_fs_streams_encoding(files_dir: str):
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)

    recip_vk_bytes, recip_sigkey_bytes = create_keypair(b'00000000000000000000000RECIPIENT')
    recip_vk, recip_sigkey = bytes_to_b58(recip_vk_bytes), bytes_to_b58(recip_sigkey_bytes)

    write_enc = StreamEncryption()
    write_enc.setup(target_verkeys=[recip_vk])
    with open(file_under_test, 'rb') as f:
        file_content = f.read()
    enc_file_path = os.path.join(files_dir, 'big_img_encrypted_stream.jpeg.bin')
    wo = FileSystemWriteOnlyStream(enc_file_path, chunk_size=1024*2, enc=write_enc)
    try:
        await wo.create(truncate=True)
        await wo.open()
        try:
            await wo.write(file_content)
            chunks_num = wo.chunks_num
        finally:
            await wo.close()
        read_enc = StreamDecryption(recipients=write_enc.recipients, nonce=write_enc.nonce)
        read_enc.setup(recip_vk, recip_sigkey)
        ro = FileSystemReadOnlyStream(enc_file_path, chunks_num=chunks_num, enc=read_enc)
        await ro.open()
        try:
            data = await ro.read()
            data_md5 = calc_bytes_hash(data)
            assert data_md5 == file_under_test_md5
        finally:
            await ro.close()
    finally:
        os.remove(enc_file_path)


@pytest.mark.asyncio
async def test_streams_encoding_layers(files_dir: str):
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)
    tmp_file_layer1 = os.path.join(tempfile.tempdir, f'layer1_{uuid.uuid4().hex}.bin')
    tmp_file_layer2 = os.path.join(tempfile.tempdir, f'layer2_{uuid.uuid4().hex}.bin')
    file_for_checks = os.path.join(tempfile.tempdir, f'checks_{uuid.uuid4().hex}.bin')
    # Layer-1
    recip_vk_bytes1, recip_sigkey_bytes1 = create_keypair(b'0000000000000000000000RECIPIENT1')
    recip_vk1, recip_sigkey1 = bytes_to_b58(recip_vk_bytes1), bytes_to_b58(recip_sigkey_bytes1)
    layers_chunk_size = 1024
    layer1 = {
        'keys': (recip_vk1, recip_sigkey1),
        'writer': FileSystemWriteOnlyStream(
            path=tmp_file_layer1,
            chunk_size=layers_chunk_size,
            enc=StreamEncryption().setup(target_verkeys=[recip_vk1])
        )
    }
    # Layer-2
    recip_vk_bytes2, recip_sigkey_bytes2 = create_keypair(b'0000000000000000000000RECIPIENT2')
    recip_vk2, recip_sigkey2 = bytes_to_b58(recip_vk_bytes2), bytes_to_b58(recip_sigkey_bytes2)
    layer2 = {
        'keys': (recip_vk2, recip_sigkey2),
        'writer': FileSystemWriteOnlyStream(
            path=tmp_file_layer2,
            chunk_size=layers_chunk_size,
            enc=StreamEncryption().setup(target_verkeys=[recip_vk2])
        )
    }
    await layer1['writer'].create(truncate=True)
    try:
        await layer2['writer'].create(truncate=True)
        try:
            with open(file_under_test, 'rb') as f:
                content_under_test = f.read()
            # Layer-2 Encrypt (upper-level)
            await layer2['writer'].open()
            await layer2['writer'].write(content_under_test)
            layer2_chunks_num = layer2['writer'].chunks_num
            await layer2['writer'].close()
            # Layer-1 Encrypt (Lower-Level)
            src = FileSystemReadOnlyStream(
                path=layer2['writer'].path, chunks_num=layer2_chunks_num, enc=StreamDecryption(type_=StreamEncType.UNKNOWN)
            )
            await src.open()
            await layer1['writer'].create(truncate=True)
            await layer1['writer'].open()
            await layer1['writer'].copy(src)
            layer1_chunks_num = layer1['writer'].chunks_num
            await layer1['writer'].close()
            await src.close()
            # Layer1 -> Layer2 decryption (lower -> upper)
            layer1_reader = FileSystemReadOnlyStream(
                path=layer1['writer'].path, chunks_num=layer1_chunks_num, enc=layer1['writer'].enc
            )
            await layer1_reader.open()
            try:
                dest = FileSystemWriteOnlyStream(
                    path=file_for_checks, chunk_size=layers_chunk_size, enc=StreamEncryption(type_=StreamEncType.UNKNOWN)
                )
                await dest.create(truncate=True)
                try:
                    await dest.open()
                    await dest.copy(layer1_reader)
                    await dest.close()
                    layer2_reader = FileSystemReadOnlyStream(
                        path=file_for_checks, chunks_num=layer2_chunks_num, enc=layer2['writer'].enc
                    )
                    await layer2_reader.open()
                    try:
                        # Check-1
                        actual_data = await layer2_reader.read()
                        actual_md5 = calc_bytes_hash(actual_data)
                        assert file_under_test_md5 == actual_md5
                        # Check-2
                        accum = b''
                        async for chunk in layer2_reader.read_chunked(src=layer1_reader):
                            accum += chunk
                        assert file_under_test_md5 == actual_md5
                    finally:
                        await layer2_reader.close()
                finally:
                    os.remove(file_for_checks)
            finally:
                await layer1_reader.close()
        finally:
            os.remove(tmp_file_layer2)
    finally:
        os.remove(tmp_file_layer1)


@pytest.mark.asyncio
async def test_streams_encoding_seeking():
    chunk_size = 1024
    actual_chunks = [
        b'0' * chunk_size,
        b'1' * chunk_size,
        b'2' * (chunk_size//2)
    ]
    replaced_chunk = b'x' * chunk_size

    recip_vk_bytes, recip_sigkey_bytes = create_keypair(b'0000000000000000000000RECIPIENT1')
    recip_vk, recip_sigkey = bytes_to_b58(recip_vk_bytes), bytes_to_b58(recip_sigkey_bytes)
    file_under_test = os.path.join(tempfile.tempdir, f'{uuid.uuid4().hex}.bin')
    open(file_under_test, 'w+b')
    try:
        writer = FileSystemWriteOnlyStream(
            path=file_under_test, chunk_size=chunk_size,
            enc=StreamEncryption(type_=StreamEncType.X25519KeyAgreementKey2019).setup(target_verkeys=[recip_vk])
        )
        # Write chunks
        await writer.open()
        try:
            for no, chunk in enumerate(actual_chunks):
                await writer.write_chunk(chunk, no)
            assert writer.chunks_num == len(actual_chunks)
        finally:
            await writer.close()
        # Read chunks
        reader = FileSystemReadOnlyStream(
            path=file_under_test, chunks_num=len(actual_chunks),
            enc=StreamDecryption(type_=StreamEncType.X25519KeyAgreementKey2019).setup(recip_vk, recip_sigkey)
        )
        await reader.open()
        try:
            for no, expected_chunk in enumerate(actual_chunks):
                actual_chunk = await reader.read_chunk()
        finally:
            await reader.close()
    finally:
        os.remove(file_under_test)


@pytest.mark.asyncio
async def test_fs_streams_encoding_copy(files_dir: str):
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)

    sender_vk_bytes, sender_sigkey_bytes = create_keypair(b'00000000000000000000000000SENDER')
    sender_vk, sender_sigkey = bytes_to_b58(sender_vk_bytes), bytes_to_b58(sender_sigkey_bytes)
    recip_vk_bytes, recip_sigkey_bytes = create_keypair(b'00000000000000000000000RECIPIENT')
    recip_vk, recip_sigkey = bytes_to_b58(recip_vk_bytes), bytes_to_b58(recip_sigkey_bytes)

    write_enc = StreamEncryption()
    write_enc.setup(target_verkeys=[recip_vk])
    with open(file_under_test, 'rb') as f:
        file_content = f.read()
    enc_file_path = os.path.join(files_dir, 'big_img_encrypted_stream.jpeg.bin')
    wo = FileSystemWriteOnlyStream(enc_file_path, chunk_size=1024, enc=write_enc)
    try:
        await wo.create(truncate=True)
        await wo.open()
        try:
            await wo.write(file_content)
        finally:
            await wo.close()
        read_enc = StreamDecryption(recipients=write_enc.recipients, nonce=write_enc.nonce)
        read_enc.setup(recip_vk, recip_sigkey)
        ro = FileSystemReadOnlyStream(enc_file_path, chunks_num=wo.chunks_num, enc=read_enc)
        await ro.open()
        try:
            enc_copy_path = os.path.join(files_dir, 'big_img_encrypted_stream_copy.jpeg')
            try:
                copy_wo = FileSystemWriteOnlyStream(enc_copy_path, chunk_size=1024)
                await copy_wo.create(truncate=True)
                await copy_wo.open()
                try:
                    await copy_wo.copy(ro)
                finally:
                    await copy_wo.close()
                copied_file_md5 = calc_file_hash(enc_copy_path)
                assert copied_file_md5 == file_under_test_md5
            finally:
                os.remove(enc_copy_path)
        finally:
            await ro.close()
    finally:
        os.remove(enc_file_path)


@pytest.mark.asyncio
async def test_readonly_stream_protocols(files_dir: str, config_c: dict, config_d: dict):
    """
    Agent-C is CALLER
    Agent-D is CALLED
    """

    caller_p2p = await get_pairwise3(me=config_c, their=config_d)
    called_p2p = await get_pairwise3(me=config_d, their=config_c)
    testing_thid = 'test-readonly-protocol-' + uuid.uuid4().hex
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    ro_chunks_num = 10
    etalon_chunks = []
    print('#')

    etalon_ro = FileSystemReadOnlyStream(path=file_under_test, chunks_num=ro_chunks_num)
    await etalon_ro.open()
    try:
        async for chunk in etalon_ro.read_chunked():
            etalon_chunks.append(chunk)
    finally:
        await etalon_ro.close()

    async def called():
        async with sirius_sdk.context(**config_d):
            stream = FileSystemReadOnlyStream(path=file_under_test, chunks_num=ro_chunks_num)
            state_machine = CalledReadOnlyStreamProtocol(called_p2p, thid=testing_thid)
            await state_machine.run_forever(stream)

    async def caller():
        async with sirius_sdk.context(**config_c):
            ro = CallerReadOnlyStreamProtocol(called=caller_p2p, uri=file_under_test, read_timeout=5, thid=testing_thid)
            # open
            await ro.open()
            # checks...
            assert ro.is_open is True
            assert ro.current_chunk == 0
            assert ro.chunks_num == ro_chunks_num
            assert ro.seekable is True
            # read
            no1, chunk1 = await ro.read_chunk()
            assert ro.current_chunk == no1
            assert etalon_chunks[no1-1] == chunk1
            no2, chunk2 = await ro.read_chunk()
            assert ro.current_chunk == no2
            assert etalon_chunks[no2-1] == chunk2
            # seeks
            no = await ro.seek_to_chunk(0)
            assert no == 0
            assert ro.current_chunk == 0
            no = await ro.seek_to_chunk(3)
            assert no == 3
            assert ro.current_chunk == 3
            # close
            await ro.close()
            assert ro.is_open is False

    results = await run_coroutines(called(), caller(), timeout=5)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_readonly_stream_protocols_chunks_and_eof(files_dir: str, config_c: dict, config_d: dict):
    """
    Agent-C is CALLER
    Agent-D is CALLED
    """

    caller_p2p = await get_pairwise3(me=config_c, their=config_d)
    called_p2p = await get_pairwise3(me=config_d, their=config_c)
    testing_thid = 'test-readonly-protocol-' + uuid.uuid4().hex
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)
    ro_chunks_num = 10

    async def called():
        async with sirius_sdk.context(**config_d):
            stream = FileSystemReadOnlyStream(path=file_under_test, chunks_num=ro_chunks_num)
            state_machine = CalledReadOnlyStreamProtocol(called_p2p, thid=testing_thid)
            await state_machine.run_forever(stream)

    async def caller():
        async with sirius_sdk.context(**config_c):
            ro = CallerReadOnlyStreamProtocol(called=caller_p2p, uri=file_under_test, read_timeout=5, thid=testing_thid)
            # open
            await ro.open()
            # checks read data md5
            read_data = await ro.read()
            assert calc_bytes_hash(read_data) == file_under_test_md5
            # check EOF
            with pytest.raises(StreamEOF):
                await ro.seek_to_chunk(1000)
            await ro.seek_to_chunk(ro_chunks_num)
            with pytest.raises(StreamEOF):
                await ro.read_chunk()
            # close
            await ro.close()

    results = await run_coroutines(called(), caller(), timeout=5)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_readonly_stream_delays(files_dir: str, config_c: dict, config_d: dict):
    """Check SWAP mechanism in non-reliable communication channel
    Agent-C is CALLER
    Agent-D is CALLED
    """
    caller_p2p = await get_pairwise3(me=config_c, their=config_d)
    called_p2p = await get_pairwise3(me=config_d, their=config_c)
    testing_thid = 'test-readonly-protocol-' + uuid.uuid4().hex
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)
    ro_chunks_num = 10

    async def called():
        async with sirius_sdk.context(**config_d):
            stream = MockedReadOnlyStream(path=file_under_test, chunks_num=ro_chunks_num)
            stream.retention_delay_sec = 1
            stream.retention_delay_limit = 2
            state_machine = CalledReadOnlyStreamProtocol(called_p2p, thid=testing_thid)
            await state_machine.run_forever(stream)

    async def caller():
        async with sirius_sdk.context(**config_c):
            ro = CallerReadOnlyStreamProtocol(
                called=caller_p2p, uri=file_under_test, read_timeout=3, retry_count=3,
                thid=testing_thid
            )
            # open
            await ro.open()
            # checks read data md5
            read_data = await ro.read()
            assert calc_bytes_hash(read_data) == file_under_test_md5
            # check EOF
            with pytest.raises(StreamEOF):
                await ro.seek_to_chunk(1000)
            await ro.seek_to_chunk(ro_chunks_num)
            with pytest.raises(StreamEOF):
                await ro.read_chunk()
            # close
            await ro.close()

    results = await run_coroutines(called(), caller(), timeout=15)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_writeonly_stream_protocols(config_c: dict, config_d: dict):
    """
    Agent-C is CALLER
    Agent-D is CALLED
    """

    caller_p2p = await get_pairwise3(me=config_c, their=config_d)
    called_p2p = await get_pairwise3(me=config_d, their=config_c)
    testing_thid = 'test-writeonly-protocol-' + uuid.uuid4().hex
    file_under_test = os.path.join(tempfile.tempdir, f'{uuid.uuid4().hex}.bin')
    chunks_num = 5
    chunk_size = 128
    etalon_chunks = []
    for n in range(chunks_num):
        s = f'{n}' * chunk_size
        etalon_chunks.append(s.encode())
    s = 'x' * (chunk_size // 2)
    etalon_chunks.append(s.encode())
    etalon_data = b''
    for b in etalon_chunks:
        etalon_data += b
    etalon_md5 = calc_bytes_hash(etalon_data)
    print('')

    async def called():
        async with sirius_sdk.context(**config_d):
            stream = FileSystemWriteOnlyStream(path=file_under_test, chunk_size=chunk_size)
            await stream.create()
            try:
                state_machine = CalledWriteOnlyStreamProtocol(called_p2p, thid=testing_thid)
                await state_machine.run_forever(stream)
            finally:
                os.remove(file_under_test)

    async def caller():
        async with sirius_sdk.context(**config_c):
            wo = CallerWriteOnlyStreamProtocol(called=caller_p2p, uri=file_under_test, thid=testing_thid)
            # open
            await wo.open()
            # checks...
            assert wo.is_open is True
            assert wo.current_chunk == 0
            assert wo.chunks_num == 0
            assert wo.seekable is True
            assert wo.chunk_size == chunk_size
            # write all
            for no, chunk in enumerate(etalon_chunks):
                new_no, sz = await wo.write_chunk(chunk, no)
                assert new_no == no + 1
                assert sz == len(chunk)
                assert wo.current_chunk == new_no
            # check MD5
            md5 = calc_file_hash(file_under_test)
            assert etalon_md5 == md5
            # close
            await wo.close()
            assert wo.is_open is False

    results = await run_coroutines(called(), caller(), timeout=5)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_writeonly_stream_write_all(config_c: dict, config_d: dict):
    """
    Agent-C is CALLER
    Agent-D is CALLED
    """

    caller_p2p = await get_pairwise3(me=config_c, their=config_d)
    called_p2p = await get_pairwise3(me=config_d, their=config_c)
    testing_thid = 'test-writeonly-protocol-' + uuid.uuid4().hex
    file_under_test = os.path.join(tempfile.tempdir, f'{uuid.uuid4().hex}.bin')
    chunk_size = 128
    data_size = chunk_size * 5 + 100
    data = b'0' * data_size
    etalon_md5 = calc_bytes_hash(data)
    print('')

    async def called():
        async with sirius_sdk.context(**config_d):
            stream = FileSystemWriteOnlyStream(path=file_under_test, chunk_size=chunk_size)
            await stream.create()
            try:
                state_machine = CalledWriteOnlyStreamProtocol(called_p2p, thid=testing_thid)
                await state_machine.run_forever(stream)
            finally:
                os.remove(file_under_test)

    async def caller():
        async with sirius_sdk.context(**config_c):
            wo = CallerWriteOnlyStreamProtocol(called=caller_p2p, uri=file_under_test, thid=testing_thid)
            # open
            await wo.open()
            # write all
            await wo.write(data)
            # check MD5
            md5 = calc_file_hash(file_under_test)
            assert etalon_md5 == md5
            # close
            await wo.close()

    results = await run_coroutines(called(), caller(), timeout=5)
    assert len(results) == 2
