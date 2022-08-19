import asyncio
import math
import os
import shutil
import string
import random
import tempfile
import uuid
from typing import Optional

import aiofiles
import pytest

import sirius_sdk
from sirius_sdk.encryption import create_keypair, bytes_to_b58
from sirius_sdk.agent.aries_rfc.feature_0750_storage import *
from sirius_sdk.agent.aries_rfc.feature_0750_storage.errors import ConfidentialStoragePermissionDenied
from sirius_sdk.recipes.confidential_storage import SimpleDataVault

from tests.helpers import calc_file_hash, calc_bytes_hash, calc_file_size, run_coroutines
from tests.conftest import get_pairwise3


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
    # 4. Write stream: append to end
    wo_file_path = os.path.join(files_dir, 'append_stream.jpeg')
    chunk_size = 1
    wo = FileSystemWriteOnlyStream(wo_file_path, chunk_size)
    await wo.create(truncate=True)
    await wo.open()
    try:
        await wo.write(b'0' * chunk_size)
        assert wo.current_chunk == 1
        await wo.close()
        wo = FileSystemWriteOnlyStream(wo_file_path, chunk_size)
        await wo.open()
        assert wo.current_chunk == 1
        await wo.write(b'1' * chunk_size)
        await wo.close()
        with open(wo_file_path, 'rb') as f:
            content = f.read()
            assert content == b'01'
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
async def test_fs_streams_truncate():
    chunks = [b'chunk1', b'chunk2', b'chunk3']
    actual_chunks_num = len(chunks)
    for trunked_to_no in [0, 1, 2, 1000]:
        file_under_test = os.path.join(tempfile.tempdir, f'truncates_for_{trunked_to_no}.bin')
        wo = FileSystemWriteOnlyStream(file_under_test, chunk_size=len(chunks[0]))
        await wo.create(truncate=True)
        try:
            await wo.open()
            try:
                assert wo.chunks_num == 0
                for no, chunk in enumerate(chunks):
                    await wo.write_chunk(chunk, no)
                assert wo.chunks_num == len(chunks)
                await wo.truncate(trunked_to_no)
                assert wo.chunks_num == min(trunked_to_no, actual_chunks_num), f'Error for trancate to {trunked_to_no}'
                assert wo.current_chunk == min(trunked_to_no, actual_chunks_num), f'Error for trancate to {trunked_to_no}'
            finally:
                await wo.close()
            with open(file_under_test, 'rb') as f:
                content = f.read()
            expected = ''.join([s.decode() for s in chunks[:trunked_to_no]]).encode()
            assert expected == content, f'Error for trancate to {trunked_to_no}'
        finally:
            os.remove(file_under_test)


@pytest.mark.asyncio
async def test_fs_streams_copy(files_dir: str):
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)
    file_under_test_size = calc_file_size(file_under_test)
    chunks_num = 5
    # 1. Reading All Data
    for chunk_size in [100, 1024, 10000000]:
        expected_chunks_num = chunks_num  # math.ceil(file_under_test_size / chunk_size)
        ro = FileSystemReadOnlyStream(file_under_test, chunks_num=chunks_num)
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
async def test_fs_streams_truncate_for_encoding():
    chunks = [b'chunk1', b'chunk2', b'chunk3']
    actual_chunks_num = len(chunks)
    for trunked_to_no in [0, 1, 2, 1000]:
        file_under_test = os.path.join(tempfile.tempdir, f'truncates_for_{trunked_to_no}.bin')
        wo = FileSystemWriteOnlyStream(
            file_under_test, chunk_size=len(chunks[0]), enc=StreamEncryption(type_=ConfidentialStorageEncType.UNKNOWN)
        )
        await wo.create(truncate=True)
        try:
            await wo.open()
            try:
                assert wo.chunks_num == 0
                for no, chunk in enumerate(chunks):
                    await wo.write_chunk(chunk, no)
                assert wo.chunks_num == len(chunks)
                await wo.truncate(trunked_to_no)
                assert wo.chunks_num == min(trunked_to_no, actual_chunks_num), f'Error for truncate to {trunked_to_no}'
                assert wo.current_chunk == min(trunked_to_no, actual_chunks_num), f'Error for truncate to {trunked_to_no}'
            finally:
                await wo.close()
            if trunked_to_no == 0:
                with open(file_under_test, 'rb') as f:
                    content = f.read()
                assert content == b''
            else:
                ro = FileSystemReadOnlyStream(
                    file_under_test, chunks_num=min(trunked_to_no, actual_chunks_num), enc=StreamDecryption(type_=ConfidentialStorageEncType.UNKNOWN)
                )
                await ro.open()
                try:
                    content = await ro.read()
                finally:
                    await ro.close()
                expected = ''.join([s.decode() for s in chunks[:trunked_to_no]]).encode()
                assert expected == content, f'Error for truncate to {trunked_to_no}'
        finally:
            os.remove(file_under_test)


@pytest.mark.asyncio
async def test_fs_streams_decoding_from_wallet1(config_c: dict):

    async with sirius_sdk.context(**config_c):
        seed = uuid.uuid4().hex[:32]
        vk = await sirius_sdk.Crypto.create_key(seed=seed)

    # Non-ASCII symbols
    chunk = "hello aåbäcö".encode()

    enc = StreamEncryption(nonce=bytes_to_b58(b'0'*12)).setup(target_verkeys=[vk])
    dec = StreamDecryption(recipients=enc.recipients, nonce=enc.nonce)

    assert dec.cek is None

    async with sirius_sdk.context(**config_c):
        w = FileSystemWriteOnlyStream(path='', chunk_size=1, enc=enc)
        r = FileSystemReadOnlyStream(path='', chunks_num=1, enc=dec)
        encoded = await w.encrypt(chunk)
        decoded = await r.decrypt(encoded)
        assert decoded == chunk


@pytest.mark.asyncio
async def test_fs_streams_decoding_from_wallet2(config_c: dict):

    async with sirius_sdk.context(**config_c):
        vk = await sirius_sdk.Crypto.create_key()

    enc = StreamEncryption().setup(target_verkeys=[vk])
    file_under_test = os.path.join(tempfile.tempdir, f'{uuid.uuid4().hex}.bin')
    chunk_size = 1024
    chunk = b'x' * chunk_size

    wo = FileSystemWriteOnlyStream(file_under_test, chunk_size=chunk_size, enc=enc)
    await wo.create(truncate=True)
    try:
        await wo.open()
        await wo.write(chunk)
        test_file_chunks_num = wo.chunks_num
        await wo.close()
        # Decoding
        dec = StreamDecryption(type_=enc.type, recipients=enc.recipients, nonce=enc.nonce)
        async with sirius_sdk.context(**config_c):
            ro = FileSystemReadOnlyStream(file_under_test, chunks_num=test_file_chunks_num, enc=dec)
            await ro.open()
            no, actual_chunk = await ro.read_chunk()
            await ro.close()
            assert actual_chunk == chunk
    finally:
        os.remove(file_under_test)


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
                path=layer2['writer'].path, chunks_num=layer2_chunks_num, enc=StreamDecryption(type_=ConfidentialStorageEncType.UNKNOWN)
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
                    path=file_for_checks, chunk_size=layers_chunk_size, enc=StreamEncryption(type_=ConfidentialStorageEncType.UNKNOWN)
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
    append_chunk = b'x' * chunk_size

    recip_vk_bytes, recip_sigkey_bytes = create_keypair(b'0000000000000000000000RECIPIENT1')
    recip_vk, recip_sigkey = bytes_to_b58(recip_vk_bytes), bytes_to_b58(recip_sigkey_bytes)
    file_under_test = os.path.join(tempfile.tempdir, f'{uuid.uuid4().hex}.bin')
    open(file_under_test, 'w+b')
    try:
        enc = StreamEncryption(
            type_=ConfidentialStorageEncType.X25519KeyAgreementKey2019).setup(target_verkeys=[recip_vk]
                                                                              )
        writer = FileSystemWriteOnlyStream(
            path=file_under_test, chunk_size=chunk_size,
            enc=enc
        )
        # Write chunks
        await writer.open()
        try:
            for no, chunk in enumerate(actual_chunks):
                await writer.write_chunk(chunk)
            assert writer.chunks_num == len(actual_chunks)
        finally:
            await writer.close()
        # Read chunks
        reader = FileSystemReadOnlyStream(
            path=file_under_test, chunks_num=len(actual_chunks),
            enc=StreamDecryption(
                recipients=writer.enc.recipients, type_=ConfidentialStorageEncType.X25519KeyAgreementKey2019, nonce=writer.enc.nonce
            ).setup(recip_vk, recip_sigkey)
        )
        await reader.open()
        try:
            for no, expected_chunk in enumerate(actual_chunks):
                new_no, actual_chunk = await reader.read_chunk(no)
                assert actual_chunk == expected_chunk
                assert new_no == no+1
        finally:
            await reader.close()
        # Append
        writer = FileSystemWriteOnlyStream(
            path=file_under_test, chunk_size=chunk_size,
            enc=enc
        )
        # Append chunk to the end of stream
        await writer.open()
        try:
            await writer.write_chunk(append_chunk)
            actual_chunks_after_append = writer.chunks_num
            assert actual_chunks_after_append == len(actual_chunks) + 1
        finally:
            await writer.close()
        reader = FileSystemReadOnlyStream(
            path=file_under_test, chunks_num=actual_chunks_after_append,
            enc=StreamDecryption(
                recipients=writer.enc.recipients, type_=ConfidentialStorageEncType.X25519KeyAgreementKey2019, nonce=writer.enc.nonce
            ).setup(recip_vk, recip_sigkey)
        )
        await reader.open()
        try:
            i = 0
            async for chunk in reader.read_chunked():
                if i < len(actual_chunks):
                    expected = actual_chunks[i]
                else:
                    expected = append_chunk
                assert chunk == expected
                i += 1
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
async def test_writeonly_stream_protocol_write_all(config_c: dict, config_d: dict):
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


@pytest.mark.asyncio
async def test_stream_protocols_encoding(config_c: dict, config_d: dict):
    """
    Agent-C is CALLER
    Agent-D is CALLED
    """

    caller_p2p = await get_pairwise3(me=config_c, their=config_d)
    called_p2p = await get_pairwise3(me=config_d, their=config_c)
    testing_thid = 'test-writeonly-protocol-encoding-' + uuid.uuid4().hex
    file_under_test = os.path.join(tempfile.tempdir, f'{uuid.uuid4().hex}.bin')

    recip_vk_bytes, recip_sigkey_bytes = create_keypair(b'00000000000000000000000RECIPIENT')
    recip_vk, recip_sigkey = bytes_to_b58(recip_vk_bytes), bytes_to_b58(recip_sigkey_bytes)
    enc = StreamEncryption().setup(target_verkeys=[recip_vk])
    dec = StreamDecryption(recipients=enc.recipients, nonce=enc.nonce)
    dec.setup(recip_vk, recip_sigkey)
    data_size = 5000
    data = b'0' * data_size

    async def called():
        async with sirius_sdk.context(**config_d):
            wo = FileSystemWriteOnlyStream(
                path=file_under_test
            )
            await wo.create()
            try:
                state_machine1 = CalledWriteOnlyStreamProtocol(called_p2p, thid=testing_thid)
                await state_machine1.run_forever(wo)

                state_machine2 = CalledReadOnlyStreamProtocol(called_p2p, thid=testing_thid)
                ro = FileSystemReadOnlyStream(
                    path=file_under_test,
                    chunks_num=wo.chunks_num
                )
                await state_machine2.run_forever(ro)
            finally:
                os.remove(file_under_test)

    async def caller():
        async with sirius_sdk.context(**config_c):
            nonlocal data
            # Write data
            wo = CallerWriteOnlyStreamProtocol(
                called=caller_p2p,
                uri=file_under_test,
                thid=testing_thid,
                enc=enc
            )
            # open
            await wo.open()
            # write all
            await wo.write(data)
            # close
            await wo.close()
            # sleep
            await asyncio.sleep(1)
            # reader
            ro = CallerReadOnlyStreamProtocol(
                called=caller_p2p,
                uri=file_under_test,
                thid=testing_thid,
                enc=dec,
                read_timeout=3
            )
            await ro.open()
            actual_data = await ro.read()
            await ro.close()
            assert actual_data == data

    results = await run_coroutines(called(), caller(), timeout=5)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_stream_protocols_truncate(config_c: dict, config_d: dict):
    """
    Agent-C is CALLER
    Agent-D is CALLED
    """

    caller_p2p = await get_pairwise3(me=config_c, their=config_d)
    called_p2p = await get_pairwise3(me=config_d, their=config_c)
    testing_thid = 'test-writeonly-protocol-encoding-' + uuid.uuid4().hex
    file_under_test = os.path.join(tempfile.tempdir, f'{uuid.uuid4().hex}.bin')

    recip_vk_bytes, recip_sigkey_bytes = create_keypair(b'00000000000000000000000RECIPIENT')
    recip_vk, recip_sigkey = bytes_to_b58(recip_vk_bytes), bytes_to_b58(recip_sigkey_bytes)
    enc = StreamEncryption().setup(target_verkeys=[recip_vk])
    dec = StreamDecryption(recipients=enc.recipients, nonce=enc.nonce)
    dec.setup(recip_vk, recip_sigkey)
    chunks = [b'chunk1', b'chunk2', b'chunk3']
    content = ''.join([s.decode() for s in chunks]).encode()

    async def called():
        async with sirius_sdk.context(**config_d):
            wo = FileSystemWriteOnlyStream(
                path=file_under_test
            )
            await wo.create()
            try:
                state_machine1 = CalledWriteOnlyStreamProtocol(called_p2p, thid=testing_thid)
                await state_machine1.run_forever(wo)

                state_machine2 = CalledReadOnlyStreamProtocol(called_p2p, thid=testing_thid)
                ro = FileSystemReadOnlyStream(
                    path=file_under_test,
                    chunks_num=wo.chunks_num
                )
                await state_machine2.run_forever(ro)
            finally:
                os.remove(file_under_test)

    async def caller():
        async with sirius_sdk.context(**config_c):
            nonlocal chunks
            # Write data
            wo = CallerWriteOnlyStreamProtocol(
                called=caller_p2p,
                uri=file_under_test,
                thid=testing_thid,
                enc=enc
            )
            # Write
            await wo.open()
            for chunk in chunks:
                await wo.write_chunk(chunk)
            await wo.truncate(1)
            await wo.close()
            # sleep
            await asyncio.sleep(1)
            # reader
            ro = CallerReadOnlyStreamProtocol(
                called=caller_p2p,
                uri=file_under_test,
                thid=testing_thid,
                enc=dec,
                read_timeout=3
            )
            await ro.open()
            actual_data = await ro.read()
            await ro.close()
            assert actual_data == chunks[0]

    results = await run_coroutines(called(), caller(), timeout=5)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_encrypted_documents(config_a: dict, config_b: dict, config_c: dict):
    """
    Agent-A + Agent-B are reader parties
    Agent-C is publisher party
    """

    # Recipient-1
    async with sirius_sdk.context(**config_a):
        recip_vk_a = await sirius_sdk.Crypto.create_key()
    # Recipient-1
    async with sirius_sdk.context(**config_b):
        recip_vk_b = await sirius_sdk.Crypto.create_key()
    # Sender
    async with sirius_sdk.context(**config_c):
        sender_vk = await sirius_sdk.Crypto.create_key()

    content = 'some-data-and-non-ascii-aåbäcö'.encode()
    document = EncryptedDocument(target_verkeys=[recip_vk_a, recip_vk_b])

    document.content = content
    assert document.content == content
    assert document.encrypted is False
    # Publisher
    async with sirius_sdk.context(**config_c):
        await document.encrypt(my_vk=sender_vk)

    assert document.content != content
    assert document.encrypted is True

    for party in [config_a, config_b]:
        async with sirius_sdk.context(**party):
            tmp = EncryptedDocument(src=document)
            await tmp.decrypt()
            assert tmp.sender_vk == sender_vk
            assert tmp.content == content


@pytest.mark.asyncio
async def test_encrypted_documents_save_load(config_a: dict):
    """
    Agent-A is reader parties
    """
    # Recipient
    async with sirius_sdk.context(**config_a):
        recip_vk = await sirius_sdk.Crypto.create_key()

    expected_content = 'some-data-and-non-ascii-aåbäcö'.encode()
    document = EncryptedDocument(target_verkeys=[recip_vk])
    document.content = expected_content

    file_under_test = os.path.join(tempfile.tempdir, f'{uuid.uuid4().hex}.bin')
    wo = FileSystemWriteOnlyStream(file_under_test)
    await wo.create(truncate=True)
    try:
        #
        await wo.open()
        try:
            await document.save(wo)
            chunks_num = wo.chunks_num
        finally:
            await wo.close()
        ro = FileSystemReadOnlyStream(file_under_test, chunks_num)
        await ro.open()
        try:
            loaded_doc = EncryptedDocument()
            await loaded_doc.load(ro)
            assert loaded_doc.content == expected_content
        finally:
            await ro.close()
    finally:
        os.remove(file_under_test)


@pytest.mark.asyncio
async def test_recipe_simple_vault_init(config_a: dict, config_b: dict):
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    p2p = await get_pairwise3(me=config_a, their=config_b)
    os.mkdir(dir_under_test)
    try:
        # Storage Hub side
        auth = ConfidentialStorageAuthProvider()
        # Check auth checks
        with pytest.raises(ConfidentialStoragePermissionDenied):
            SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
        await auth.authorize(p2p)
        assert auth.authorized is True
        # Check init
        vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
        assert vault.cfg is not None
        assert vault.cfg.as_json() != {}
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_recipe_simple_stream_operations(config_a: dict, config_b: dict):
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    p2p = await get_pairwise3(me=config_a, their=config_b)
    os.mkdir(dir_under_test)
    uri_under_test = f'stream_{uuid.uuid4().hex}.bin'
    test_data = b'x' * 1024 * 5
    try:
        # Storage Hub side
        async with sirius_sdk.context(**config_a):
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2p)
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            print('#1')
            await vault.create_stream(uri_under_test)
            print('#2')
            stream_to_write = await vault.writable(uri_under_test)
            await stream_to_write.open()
            try:
                await stream_to_write.write(test_data)
            finally:
                await stream_to_write.close()
            print('#3')
            stream_to_read = await vault.readable(uri_under_test)
            assert stream_to_read.chunks_num > 0
            await stream_to_read.open()
            try:
                read_data = await stream_to_read.read()
            finally:
                await stream_to_read.close()
            print('#4')
            assert read_data == test_data
            file_uri = stream_to_read.path
            print('#5')
        # Check data is encrypted
        with open(file_uri, 'rb') as f:
            raw_content = f.read()
        assert raw_content != test_data
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_recipe_simple_docs_operations(config_a: dict, config_b: dict):
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    p2p = await get_pairwise3(me=config_a, their=config_b)
    os.mkdir(dir_under_test)
    uri_under_test = f'stream_{uuid.uuid4().hex}.bin'
    test_data = b'Some user content'
    try:
        # Storage Hub side
        async with sirius_sdk.context(**config_a):
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2p)
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            print('#1')
            await vault.create_document(uri_under_test)
            print('#2')
            # Store non-encrypted doc
            doc = EncryptedDocument()
            doc.content = test_data
            await vault.save(uri_under_test, doc)
            print('#3')
            loaded_doc = await vault.load(uri_under_test)
            assert loaded_doc.content == test_data
            assert loaded_doc.encrypted is False
            # Encrypted doc
            async with sirius_sdk.context(**config_b):
                recipient_vk = await sirius_sdk.Crypto.create_key()
            enc_doc = EncryptedDocument(target_verkeys=[recipient_vk])
            enc_doc.content = test_data
            print('#4')
            await enc_doc.encrypt()
            await vault.save(uri_under_test, enc_doc)
            print('#5')
            loaded_enc_doc = await vault.load(uri_under_test)
            assert loaded_enc_doc.encrypted is True
            assert loaded_enc_doc.content != test_data
            async with sirius_sdk.context(**config_b):
                await loaded_enc_doc.decrypt()
                assert loaded_enc_doc.content == test_data
    finally:
        shutil.rmtree(dir_under_test)
