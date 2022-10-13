import asyncio
import io
import json
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
from sirius_sdk.errors.indy_exceptions import WalletItemAlreadyExists
from sirius_sdk.encryption import create_keypair, bytes_to_b58
from sirius_sdk.agent.aries_rfc.feature_0750_storage import *
from sirius_sdk.agent.aries_rfc.feature_0750_storage.messages import BaseConfidentialStorageMessage, StreamOperation
from sirius_sdk.agent.aries_rfc.feature_0750_storage.errors import *
from sirius_sdk.agent.aries_rfc.feature_0750_storage.state_machines import CallerEncryptedDataVault, CalledEncryptedDataVault
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
async def test_fs_streams_encoding_with_jwe(files_dir: str):
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)

    recip_vk_bytes1, recip_sigkey_bytes1 = create_keypair(b'0000000000000000000000RECIPIENT1')
    recip_vk1, recip_sigkey1 = bytes_to_b58(recip_vk_bytes1), bytes_to_b58(recip_sigkey_bytes1)
    recip_vk_bytes2, recip_sigkey_bytes2 = create_keypair(b'0000000000000000000000RECIPIENT2')
    recip_vk2, recip_sigkey2 = bytes_to_b58(recip_vk_bytes2), bytes_to_b58(recip_sigkey_bytes2)

    write_enc = StreamEncryption()
    write_enc.setup(target_verkeys=[recip_vk1, recip_vk2])
    jwe = write_enc.jwe
    print('')

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

        for recip_vk, recip_sigkey in [(recip_vk1, recip_sigkey1), (recip_vk2, recip_sigkey2)]:
            read_enc = StreamDecryption()
            read_enc.jwe = jwe
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
async def test_fs_storage(files_dir: str, config_a: dict):
    uri_under_test = 'document.bin'
    test_data = b'Test-Data'
    path = os.path.join(files_dir, uri_under_test)
    stored_jwe = None
    stored_cek = None
    if os.path.isfile(path):
        os.remove(path)
    try:
        async with sirius_sdk.context(**config_a):
            vk = await sirius_sdk.Crypto.create_key()
            enc1 = StreamEncryption()
            enc1.setup(target_verkeys=[vk])
            stored_jwe = enc1.jwe
            stored_cek = enc1.cek
            storage = FileSystemRawByteStorage(enc1)
            await storage.mount(files_dir)
            await storage.create(uri_under_test)
            wo = await storage.writeable(uri_under_test)
            await wo.open()
            await wo.write(test_data)
            await wo.close()
            ro = await storage.readable(uri_under_test, chunks_num=wo.chunks_num)
            await ro.open()
            try:
                actual_data = await ro.read()
            except Exception as e:
                raise e
            await ro.close()
            assert actual_data == test_data
            # RE-Create storage for same JWE
            enc2 = StreamEncryption.from_jwe(stored_jwe, stored_cek)
            storage = FileSystemRawByteStorage(enc2)
            await storage.mount(files_dir)
            ro = await storage.readable(uri_under_test, chunks_num=wo.chunks_num)
            await ro.open()
            actual_data = await ro.read()
            await ro.close()
            assert actual_data == test_data
            wo = await storage.writeable(uri_under_test)
            await wo.open()
            await wo.truncate()
            try:
                await wo.write(test_data)
            except Exception as e:
                raise e
            await wo.close()
            ro = await storage.readable(uri_under_test, chunks_num=wo.chunks_num)
            await ro.open()
            try:
                actual_data = await ro.read()
            except Exception as e:
                raise
            await ro.close()
            assert actual_data == test_data
    finally:
        if os.path.isfile(path):
            os.remove(path)


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
async def test_fs_streams_decoding_from_wallet1(files_dir: str, config_c: dict):
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')

    async with sirius_sdk.context(**config_c):
        seed = uuid.uuid4().hex[:32]
        vk = await sirius_sdk.Crypto.create_key(seed=seed)

    # Non-ASCII symbols
    # chunk = "hello aåbäcö".encode()
    with open(file_under_test, 'rb') as f:
        chunk = f.read()
        chunk = chunk[:100]

    enc = StreamEncryption(nonce=bytes_to_b58(b'0'*12)).setup(target_verkeys=[vk])
    dec = StreamDecryption(recipients=enc.recipients, nonce=enc.nonce)

    # 1. Test enc/dec
    assert dec.cek is None

    async with sirius_sdk.context(**config_c):
        w = FileSystemWriteOnlyStream(path='', chunk_size=1, enc=enc)
        r = FileSystemReadOnlyStream(path='', chunks_num=1, enc=dec)
        encoded = await w.encrypt(chunk)
        decoded = await r.decrypt(encoded)
        assert decoded == chunk

    # 2. Test with JWE
    jwe = enc.jwe
    js = jwe.as_json()
    restored_jwe = JWE()
    restored_jwe.from_json(js)
    dec = StreamDecryption.from_jwe(restored_jwe)
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
async def test_streams_encoding_decoding_wrappers(files_dir: str, config_a: dict):
    # Layer-2
    target_vk, target_sk = create_keypair(seed='00000000000000000000000000TARGET'.encode())
    target_vk, target_sk = bytes_to_b58(target_vk), bytes_to_b58(target_sk)
    # Layer-1
    storage_vk, storage_sk = create_keypair(seed='0000000000000000000000000STORAGE'.encode())
    storage_vk, storage_sk = bytes_to_b58(storage_vk), bytes_to_b58(storage_sk)
    # File on Disk
    test_data = b'data*' * 1024
    storage_file = os.path.join(files_dir, 'big_img_encrypted_stream.jpeg.bin')
    # Create write-stream on Layer-1
    wo = FileSystemWriteOnlyStream(
        storage_file, chunk_size=1024, enc=StreamEncryption().setup(target_verkeys=[storage_vk])
    )
    jwe_layer1 = wo.enc.jwe
    await wo.create(truncate=True)
    try:
        # Wrap with stream abstraction on Layer-2
        enc = StreamEncryption().setup(target_verkeys=[target_vk])
        jwe = enc.jwe
        enc_restored = StreamEncryption.from_jwe(jwe)
        wrapper_to_write = WriteOnlyStreamEncodingWrapper(
            dest=wo, enc=enc_restored
        )
        jwe_layer2 = wrapper_to_write.enc.jwe
        await wrapper_to_write.open()
        try:
            await wrapper_to_write.write(test_data)
        finally:
            await wrapper_to_write.close()
        # Open Read stream on Layer-1
        ro = FileSystemReadOnlyStream(
            storage_file, chunks_num=wo.chunks_num,
            enc=StreamDecryption.from_jwe(jwe_layer1).setup(storage_vk, storage_sk)
        )
        # Wrap with stream abstraction on Layer-2
        wrapper_to_read = ReadOnlyStreamDecodingWrapper(
            src=ro,
            enc=StreamDecryption.from_jwe(jwe_layer2).setup(target_vk, target_sk)
        )
        await wrapper_to_read.open()
        try:
            actual_data = await wrapper_to_read.read()
            assert actual_data == test_data
        finally:
            await wrapper_to_read.close()
        # Wrap with stream on Layer-2 via sirius_sdk.Crypto
        async with sirius_sdk.context(**config_a):
            try:
                await sirius_sdk.Crypto.create_key(seed='00000000000000000000000000TARGET')
            except WalletItemAlreadyExists:
                pass
            wrapper_to_read = ReadOnlyStreamDecodingWrapper(
                src=ro,
                enc=StreamDecryption.from_jwe(jwe_layer2)
            )
            await wrapper_to_read.open()
            try:
                actual_data = await wrapper_to_read.read()
                assert actual_data == test_data
            finally:
                await wrapper_to_read.close()
    finally:
        os.remove(storage_file)


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
async def test_readonly_stream_protocol_persistance(files_dir: str, config_c: dict, config_d: dict):
    """Check readonly stream persistent mechanism
        Agent-C is CALLER
        Agent-D is CALLED
        """
    caller_p2p = await get_pairwise3(me=config_c, their=config_d)
    called_p2p = await get_pairwise3(me=config_d, their=config_c)
    testing_thid = 'test-readonly-protocol-' + uuid.uuid4().hex
    persist_id = 'persist_' + uuid.uuid4().hex
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)
    ro_chunks_num = 10

    async def called():
        async with sirius_sdk.context(**config_d):
            co = await sirius_sdk.spawn_coprotocol()
            await co.subscribe(testing_thid)
            try:
                while True:
                    # Pull message
                    e = await co.get_message()
                    # Every time create empty state machine instance
                    state_machine = CalledReadOnlyStreamProtocol(
                        called_p2p,
                        thid=testing_thid,
                        persistent_id=persist_id,
                        # create new stream instance (with empty state)
                        proxy_to=FileSystemReadOnlyStream(path=file_under_test, chunks_num=ro_chunks_num)
                    )
                    # load state
                    await state_machine.load()
                    await state_machine.handle(e.message)
                    if state_machine.edited:
                        # save state if need
                        await state_machine.save()
                    if e.message.operation == StreamOperation.OperationCode.CLOSE:
                        await state_machine.abort()
                        return
            finally:
                await co.abort()

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
async def test_writeonly_stream_protocol_persistance(config_c: dict, config_d: dict):
    """Check writeonly stream persistent mechanism
    Agent-C is CALLER
    Agent-D is CALLED
    """

    caller_p2p = await get_pairwise3(me=config_c, their=config_d)
    called_p2p = await get_pairwise3(me=config_d, their=config_c)
    testing_thid = 'test-writeonly-protocol-' + uuid.uuid4().hex
    file_under_test = os.path.join(tempfile.tempdir, f'{uuid.uuid4().hex}.bin')
    etalon_data = b'x' * 1024 * 3
    persist_id = uuid.uuid4().hex
    etalon_md5 = calc_bytes_hash(etalon_data)
    print('')

    async def called():
        async with sirius_sdk.context(**config_d):
            stream = FileSystemWriteOnlyStream(path=file_under_test)
            await stream.create()
            co = await sirius_sdk.spawn_coprotocol()
            await co.subscribe(testing_thid)
            try:
                while True:
                    # Pull message
                    e = await co.get_message()
                    # Every time create empty state machine instance
                    state_machine = CalledWriteOnlyStreamProtocol(
                        called_p2p,
                        thid=testing_thid,
                        persistent_id=persist_id,
                        # create new stream instance (with empty state)
                        proxy_to=FileSystemWriteOnlyStream(path=file_under_test)
                    )
                    # load state
                    await state_machine.load()
                    await state_machine.handle(e.message)
                    if state_machine.edited:
                        # save state if need
                        await state_machine.save()
                    if e.message.operation == StreamOperation.OperationCode.CLOSE:
                        await state_machine.abort()
                        return
            finally:
                await co.abort()
                os.remove(file_under_test)

    async def caller():
        async with sirius_sdk.context(**config_c):
            wo = CallerWriteOnlyStreamProtocol(called=caller_p2p, uri=file_under_test, thid=testing_thid)
            # open
            await wo.open()
            await wo.write(etalon_data)
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
            assert set(tmp.target_verkeys) == set([recip_vk_a, recip_vk_b])
            await tmp.encrypt()  # encrypt again


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
async def test_recipe_simple_datavault_stream_operations(config_a: dict, config_b: dict):
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    p2p = await get_pairwise3(me=config_a, their=config_b)
    os.mkdir(dir_under_test)
    path_under_test = f'stream_{uuid.uuid4().hex}.bin'
    test_data = b'x' * 1024 * 5
    try:
        # Storage Hub side
        async with sirius_sdk.context(**config_a):
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2p)
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            await vault.open()
            print('#1')
            doc = await vault.create_stream(path_under_test)
            uri_under_test = doc.id
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
        await vault.close()
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_recipe_simple_datavault_chunks_consistency_for_encoding_streams(files_dir: str, config_a: dict, config_b: dict):
    """If vault does not apply an encryption on self side then data will be stored without chunk offset metadata
      Stream instance should work around and restore chunk implicitly
    """
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    p2p = await get_pairwise3(me=config_a, their=config_b)
    os.mkdir(dir_under_test)
    path_under_test = f'stream_{uuid.uuid4().hex}.bin'
    chunk_size = 10*1024
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    expected_chunks = []
    with open(file_under_test, 'rb') as f:
        buffer = io.BytesIO(f.read())
    while True:
        chunk = buffer.read(chunk_size)
        if chunk:
            expected_chunks.append(chunk)
        else:
            break
    try:
        async with sirius_sdk.context(**config_a):
            # Encryption metadata
            target_vk = await sirius_sdk.Crypto.create_key()
            enc = sirius_sdk.aries_rfc.StreamEncryption().setup(target_verkeys=[p2p.me.verkey])
            jwe = enc.jwe
            cek = enc.cek
            # Vault init
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2p)
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            # vault.cfg.key_agreement.type = ConfidentialStorageEncType.UNKNOWN.value
            vault.cfg.key_agreement = None
            # Operations
            await vault.open()
            print('#1')
            # Write chunks to stream
            sd = await vault.create_stream(path_under_test)
            wo = await sd.stream.writable(jwe, cek)
            await wo.open()
            try:
                for chunk in expected_chunks:
                    await wo.write_chunk(chunk)
            finally:
                await wo.close()
            # REad chunks from stream
            print('#2')
            sd = await vault.load(sd.id)
            ro = await sd.stream.readable(jwe)
            await ro.open()
            try:
                actual_chunks = []
                async for chunk in ro.read_chunked():
                    actual_chunks.append(chunk)
            finally:
                await ro.close()
            # Checks
            print('#3')
            assert len(actual_chunks) == len(expected_chunks)
            for i, expected in enumerate(expected_chunks):
                actual = actual_chunks[i]
                assert expected == actual
        await vault.close()
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_recipe_simple_datavault_docs_operations(config_a: dict, config_b: dict):
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    p2p = await get_pairwise3(me=config_a, their=config_b)
    os.mkdir(dir_under_test)
    path_under_test = f'stream_{uuid.uuid4().hex}.bin'
    test_data = b'Some user content'
    try:
        # Storage Hub side
        async with sirius_sdk.context(**config_a):
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2p)
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            await vault.open()
            print('#1')
            doc = await vault.create_document(path_under_test)
            uri_under_test = doc.id
            print('#2')
            # Store non-encrypted doc
            doc = EncryptedDocument()
            doc.content = test_data
            await vault.save_document(uri_under_test, doc)
            print('#3')
            loaded_doc = await vault.load(uri_under_test)
            assert isinstance(loaded_doc, StructuredDocument)
            assert isinstance(loaded_doc.content, EncryptedDocument)
            assert loaded_doc.content.content == test_data
            assert loaded_doc.content.encrypted is False
            # Encrypted doc
            async with sirius_sdk.context(**config_b):
                recipient_vk = await sirius_sdk.Crypto.create_key()
            enc_doc = EncryptedDocument(target_verkeys=[recipient_vk])
            enc_doc.content = test_data
            print('#4')
            await enc_doc.encrypt()
            await vault.save_document(uri_under_test, enc_doc)
            print('#5')
            loaded_enc_doc = await vault.load(uri_under_test)
            assert isinstance(loaded_enc_doc, StructuredDocument)
            assert isinstance(loaded_enc_doc.content, EncryptedDocument)
            assert loaded_enc_doc.content.encrypted is True
            assert loaded_enc_doc.content.content != test_data
            async with sirius_sdk.context(**config_b):
                await loaded_enc_doc.content.decrypt()
                assert loaded_enc_doc.content.content == test_data
            await vault.close()
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_recipe_simple_datavault_metadata_and_indexes(config_a: dict, config_b: dict):
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    p2p = await get_pairwise3(me=config_a, their=config_b)
    os.mkdir(dir_under_test)
    test_data = b'Some user content'
    path_under_test1 = f'document_{uuid.uuid4().hex}.bin'
    path_under_test2 = f'stream_{uuid.uuid4().hex}.bin'
    attr1_val = 'attr1-' + uuid.uuid4().hex
    attr2_val = 'attr2-' + uuid.uuid4().hex
    try:
        # Storage Hub side
        async with sirius_sdk.context(**config_a):
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2p)
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            await vault.open()
            doc = await vault.create_document(path_under_test1, meta={'meta1': 'value1'}, attr1=attr1_val)
            uri_under_test1 = doc.id
            stream = await vault.create_stream(path_under_test2, meta={'contentType': 'video/mpeg'}, attr2=attr2_val)
            uri_under_test2 = stream.id
            # check1
            load_for_doc = await vault.load(uri_under_test1)
            assert isinstance(load_for_doc, StructuredDocument)
            assert isinstance(load_for_doc.content, EncryptedDocument)
            assert load_for_doc.meta['meta1'] == 'value1'
            assert 'created' in load_for_doc.meta
            assert load_for_doc.urn
            assert load_for_doc.indexed and load_for_doc.indexed[0].attributes == ['attr1']
            # check2
            load_for_stream = await vault.load(uri_under_test2)
            assert isinstance(load_for_stream, StructuredDocument)
            ro = await load_for_stream.stream.readable()
            assert isinstance(ro, AbstractReadOnlyStream)
            wo = await load_for_stream.stream.writable()
            assert isinstance(wo, AbstractWriteOnlyStream)
            assert load_for_stream.meta['contentType'] == 'video/mpeg'
            assert 'created' in load_for_stream.meta
            assert 'chunks' in load_for_stream.meta and type(load_for_stream.meta['chunks']) is int
            assert load_for_stream.urn
            assert load_for_doc.indexed and load_for_stream.indexed[0].attributes == ['attr2']
            stream_to_write = await vault.writable(uri_under_test2)
            await stream_to_write.open()
            try:
                await stream_to_write.write(test_data)
            finally:
                await stream_to_write.close()
            load_for_stream2 = await vault.load(uri_under_test2)
            assert load_for_stream2.meta['chunks'] > 0
            # Check indexes
            indexes = await vault.indexes()
            assert indexes
            collection1 = await indexes.filter(attr1=attr1_val)
            assert len(collection1) == 1
            collection2 = await indexes.filter(attr2=attr2_val)
            assert len(collection2) == 1
            collection3 = await indexes.filter(attr1=attr1_val, attr2=attr2_val)
            assert len(collection3) == 0
            await vault.close()
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_recipe_simple_datavault_update_metadata_and_attributes(config_a: dict, config_b: dict):
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    p2p = await get_pairwise3(me=config_a, their=config_b)
    os.mkdir(dir_under_test)
    path_under_test_doc = f'document_{uuid.uuid4().hex}.bin'
    path_under_test_stream = f'stream_{uuid.uuid4().hex}.bin'
    attr1_val = 'attr1'
    attr2_val = 'attr2'
    meta1 = 'meta1'
    meta2 = 'meta2'
    try:
        # Storage Hub side
        async with sirius_sdk.context(**config_a):
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2p)
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            await vault.open()
            # Create
            doc = await vault.create_document(path_under_test_doc, meta={'meta1': meta1}, attr1=attr1_val)
            uri_under_test_doc = doc.id
            stream = await vault.create_stream(path_under_test_stream, meta={'meta1': meta1}, attr1=attr1_val)
            uri_under_test_stream = stream.id
            # Update
            await vault.update(uri_under_test_doc, meta={'meta2': meta2}, attr2=attr2_val)
            await vault.update(uri_under_test_stream, meta={'meta2': meta2, 'contentType': 'video/mpeg'}, attr2=attr2_val)
            # Checks
            load_for_doc = await vault.load(uri_under_test_doc)
            assert load_for_doc.meta['meta2'] == meta2
            assert 'meta1' not in load_for_doc.meta
            assert 'created' in load_for_doc.meta
            assert load_for_doc.urn
            assert load_for_doc.indexed and load_for_doc.indexed[0].attributes == ['attr2']
            # check2
            load_for_stream = await vault.load(uri_under_test_stream)
            assert load_for_stream.meta['meta2'] == meta2
            assert 'meta1' not in load_for_stream.meta
            assert 'created' in load_for_stream.meta
            assert 'chunks' in load_for_stream.meta
            assert load_for_stream.urn
            assert load_for_stream.meta['contentType'] == 'video/mpeg'
            assert load_for_stream.indexed and load_for_doc.indexed[0].attributes == ['attr2']
            await vault.close()
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_recipe_simple_datavault_access_with_url_and_urn(config_a: dict, config_b: dict):
    """Check user can load documents/streams both with URI and URN value"""
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    p2p = await get_pairwise3(me=config_a, their=config_b)
    os.mkdir(dir_under_test)
    path_under_test_doc = f'document_{uuid.uuid4().hex}.bin'
    path_under_test_stream = f'stream_{uuid.uuid4().hex}.bin'
    try:
        # Storage Hub side
        async with sirius_sdk.context(**config_a):
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2p)
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            await vault.open()
            # Create
            created_doc = await vault.create_document(path_under_test_doc)
            uri_under_test_doc = created_doc.id
            # Load with URI
            doc_via_uri = await vault.load(uri_under_test_doc)
            doc_via_urn = await vault.load(doc_via_uri.urn)
            assert doc_via_uri.id == doc_via_urn.id == created_doc.id
            assert doc_via_uri.urn == doc_via_urn.urn == created_doc.urn
            # Repeat ones for Stream
            created_stream = await vault.create_document(path_under_test_stream)
            uri_under_test_stream = created_stream.id
            stream_via_uri = await vault.load(uri_under_test_stream)
            stream_via_urn = await vault.load(stream_via_uri.urn)
            assert stream_via_uri.id == stream_via_urn.id == created_stream.id
            assert stream_via_uri.urn == stream_via_urn.urn == created_stream.urn
            await vault.close()
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_structured_document_attach(config_a: dict):
    sd = StructuredDocumentAttach(id='document-id')
    async with sirius_sdk.context(**config_a):
        js = {
            "id": "urn:uuid:41289468-c42c-4b28-adb0-bf76044aec77",
            "sequence": 0,
            "indexed": [
                {
                    "sequence": 0,
                    "attributes": [
                    ]
                }
            ],
            "meta": {
                "created": "2019-06-19",
                "contentType": "video/mpeg",
                "chunks": 16,
            },
            "stream": {
                "id": "https://example.com/encrypted-data-vaults/zMbxmSDn2Xzz?hl=zb47JhaKJ3hJ5Jkw8oan35jK23289Hp",
            },
            "content": {
                "message": "Hello World!"
            }
        }
        sd.from_json(js)
        assert sd.id == 'https://example.com/encrypted-data-vaults/zMbxmSDn2Xzz?hl=zb47JhaKJ3hJ5Jkw8oan35jK23289Hp'
        assert sd.urn == 'urn:uuid:41289468-c42c-4b28-adb0-bf76044aec77'
        assert sd.sequence == 0
        assert sd.meta.created == '2019-06-19'
        assert sd.meta.content_type == 'video/mpeg'
        assert sd.meta.chunks == 16
        assert sd.stream.id == 'https://example.com/encrypted-data-vaults/zMbxmSDn2Xzz?hl=zb47JhaKJ3hJ5Jkw8oan35jK23289Hp'
        assert sd.document.encrypted is False
        assert sd.document.content == "Hello World!"

        target_vk = await sirius_sdk.Crypto.create_key()
        packed = await sirius_sdk.Crypto.pack_message({"message": "Hello World!"}, recipient_verkeys=[target_vk])
        js = {
            "id": "urn:uuid:41289468-c42c-4b28-adb0-bf76044aec77",
            "jwm": json.loads(packed.decode())
        }
        sd.from_json(js)
        assert sd.id == 'urn:uuid:41289468-c42c-4b28-adb0-bf76044aec77'
        assert sd.sequence is None
        assert sd.meta is None
        assert sd.stream is None
        assert sd.document.encrypted is True
        await sd.document.decrypt()
        assert sd.document.content == {"message": "Hello World!"}


@pytest.mark.asyncio
async def test_simple_datavault_critical_ops(config_a: dict, config_b: dict):
    p2p = await get_pairwise3(me=config_a, their=config_b)
    path = f'doc_{uuid.uuid4().hex}.bin'
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    os.mkdir(dir_under_test)
    try:
        async with sirius_sdk.context(**config_a):
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2p)
            # Init and configure Vault
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            await vault.open()
            # Case-1: create doc twice
            doc = await vault.create_document(path)
            assert doc.id.startswith('file://')
            uri = doc.id
            # check uri has absolute nature
            with pytest.raises(DataVaultCreateResourceError):
                await vault.create_document(uri)
            await vault.load(uri)
            # Case-2: remove file physically but meta cached in storage
            path_under_test = os.path.join(dir_under_test, vault.mounted_dir, path)
            os.remove(path_under_test)
            with pytest.raises(DataVaultResourceMissing):
                await vault.load(uri)
            await vault.create_document(uri)
            await vault.load(uri)
            # Case-3: remove
            await vault.remove(uri)
            assert os.path.isfile(path_under_test) is False
            with pytest.raises(DataVaultResourceMissing):
                await vault.load(uri)
            # Case-4: Relative path
            for uri in [f'/dir/subdir/doc_{uuid.uuid4().hex}.bin', f'dir/subdir/doc_{uuid.uuid4().hex}.bin']:
                _ = await vault.create_document(uri)
                assert uri in _.id
            # Clear
            await vault.close()
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_simple_datavault_reopen(config_a: dict, config_b: dict):
    p2p = await get_pairwise3(me=config_a, their=config_b)
    path = f'doc_{uuid.uuid4().hex}.bin'
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    os.mkdir(dir_under_test)
    try:
        async with sirius_sdk.context(**config_a):
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2p)
            # Init and configure Vault
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            await vault.open()
            # Case-1: create doc twice
            sd = await vault.create_document(path)
            doc = EncryptedDocument(content=b'Test content')
            await vault.save_document(sd.id, doc)
            loaded = await vault.load(sd.id)
            assert loaded.doc.content == b'Test content'
            # Clear
            await vault.close()
            # Reopen
            await vault.open()
            loaded = await vault.load(sd.id)
            assert loaded.doc.content == b'Test content'
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_simple_datavault_multiple_contexts(config_a: dict, config_b: dict):
    p2pa = await get_pairwise3(me=config_a, their=config_b)
    p2pb = await get_pairwise3(me=config_b, their=config_a)
    path = f'doc_{uuid.uuid4().hex}.bin'
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    os.mkdir(dir_under_test)
    try:
        async with sirius_sdk.context(**config_a):
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2pa)
            # Init and configure Vault
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            await vault.open()
            # create doc
            doc1 = await vault.create_document(path)
        async with sirius_sdk.context(**config_b):
            auth = ConfidentialStorageAuthProvider()
            await auth.authorize(p2pb)
            # Init and configure Vault
            vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
            await vault.open()
            # create doc
            doc2 = await vault.create_document(path)

        assert doc1.id == doc2.id

    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_recipe_simple_datavault_encryption_layers_for_documents(config_a: dict, config_b: dict):
    """Check encryption levels:
        - vault encrypt + controller don't encrypt on self side (trust to vault)
        - vault encrypt + controller encrypt data over vault config
        - vault don't encrypt + controller encrypt on self side (it can share encrypted data among pairwises)
        - vault don't encrypt + controller don't encrypt on self side

    P.S. Controller is participant who control data semantic
    """
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    p2p = await get_pairwise3(me=config_a, their=config_b)
    vault_config = config_a
    controller_config = config_b
    test_data = b'xxx' * 1024

    async with sirius_sdk.context(**controller_config):
        controller_encrypt_key = await sirius_sdk.Crypto.create_key()

    try:
        os.mkdir(dir_under_test)
        for case_vault_encrypt, case_controller_encrypt in [(False, False), (False, True), (True, False), (True, True)]:
            path_under_test = f'document_{uuid.uuid4().hex}.bin'
            async with sirius_sdk.context(**vault_config):
                auth = ConfidentialStorageAuthProvider()
                await auth.authorize(p2p)
                # Init and configure Vault
                vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
                if case_vault_encrypt is False:
                    vault.cfg.key_agreement = None
                await vault.open()
                # Test docs
                structured_doc = await vault.create_document(path_under_test)
                structured_doc_file_path = os.path.join(dir_under_test, vault.mounted_dir, path_under_test)
                assert os.path.isfile(structured_doc_file_path)
                if case_controller_encrypt:
                    doc = EncryptedDocument(target_verkeys=[controller_encrypt_key])
                    doc.content = test_data
                    async with sirius_sdk.context(**controller_config):
                        await doc.encrypt()
                else:
                    doc = EncryptedDocument()
                    doc.content = test_data

                await vault.save_document(structured_doc.urn, doc)

                # Case 1
                if case_vault_encrypt is False and case_controller_encrypt is False:
                    # If both parties don't encrypt data so it is raw data stored on disk
                    with open(structured_doc_file_path, 'rb') as f:
                        actual_data = f.read()
                        assert actual_data == test_data
                else:
                    # If vault is encrypted OR controller does encrypt, then data is encrypted on Disk
                    with open(structured_doc_file_path, 'rb') as f:
                        actual_data = f.read()
                        # Data on disk is encrypted
                        assert actual_data != test_data

                # Case 2
                if case_vault_encrypt is True and case_controller_encrypt is False:
                    # Data if read in Vault context is decrypted
                    loaded_doc = await vault.load(structured_doc.id)
                    assert loaded_doc.content.content == test_data

                # Case 3
                if case_vault_encrypt is False and case_controller_encrypt is True:
                    # Doc controller has access to document content
                    loaded_doc = await vault.load(structured_doc.id)
                    async with sirius_sdk.context(**controller_config):
                        await loaded_doc.content.decrypt()
                        assert loaded_doc.content.content == test_data
                        assert loaded_doc.content.encrypted is False
                # Case 4
                if case_vault_encrypt is True and case_controller_encrypt is True:
                    # Vault side don/t have access to data
                    loaded_doc = await vault.load(structured_doc.id)
                    loaded_doc.content.encrypted = True
                    assert loaded_doc.content.content != test_data
                    with pytest.raises(Exception):
                        await loaded_doc.content.decrypt()
                    # Doc controller has access to document content
                    async with sirius_sdk.context(**controller_config):
                        await loaded_doc.content.decrypt()
                        assert loaded_doc.content.content == test_data
                        assert loaded_doc.content.encrypted is False

                await vault.close()
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_recipe_simple_datavault_encryption_layers_for_streams(config_a: dict, config_b: dict):
    """Check encryption levels:
        - vault encrypt + controller don't encrypt on self side (trust to vault)
        - vault encrypt + controller encrypt data over vault config
        - vault don't encrypt + controller encrypt on self side (it can share encrypted data among pairwises)
        - vault don't encrypt + controller don't encrypt on self side

    P.S. Controller is participant who control data semantic
    """
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    p2p = await get_pairwise3(me=config_a, their=config_b)
    vault_config = config_a
    test_data = b'xxx' * 1024
    controller_pk, controller_sk = create_keypair(seed='0000000000000000000000CONTROLLER'.encode())
    controller_pk, controller_sk = bytes_to_b58(controller_pk), bytes_to_b58(controller_sk)

    try:
        os.mkdir(dir_under_test)
        for case_vault_encrypt, case_controller_encrypt in [(False, False), (False, True), (True, False), (True, True)]:
            path_under_test = f'document_{uuid.uuid4().hex}.bin'
            async with sirius_sdk.context(**vault_config):
                auth = ConfidentialStorageAuthProvider()
                await auth.authorize(p2p)
                # Init and configure Vault
                vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
                if case_vault_encrypt is False:
                    vault.cfg.key_agreement = None
                await vault.open()

                # Test stream
                structured_doc = await vault.create_stream(path_under_test)
                structured_doc_file_path = os.path.join(dir_under_test, vault.mounted_dir, path_under_test)
                assert os.path.isfile(structured_doc_file_path)
                stream_to_write_layer1 = await vault.writable(structured_doc.id)
                if case_controller_encrypt:
                    stream_to_write_layer2 = WriteOnlyStreamEncodingWrapper(
                        dest=stream_to_write_layer1,
                        enc=StreamEncryption().setup(target_verkeys=[controller_pk])
                    )
                    jwe_layer2 = stream_to_write_layer2.enc.jwe
                else:
                    # Ignore adv encoding layer
                    stream_to_write_layer2 = stream_to_write_layer1
                    jwe_layer2 = None
                # Write Data to stream under test
                await stream_to_write_layer2.open()
                await stream_to_write_layer2.write(test_data)
                await stream_to_write_layer2.close()

                # Run Test cases

                # Case 1
                if case_vault_encrypt is False and case_controller_encrypt is False:
                    # If both parties don't encrypt data so it is raw data stored on disk
                    with open(structured_doc_file_path, 'rb') as f:
                        actual_data = f.read()
                        assert actual_data == test_data
                else:
                    # If vault is encrypted or controller is encrypt, then data is encrypted
                    with open(structured_doc_file_path, 'rb') as f:
                        actual_data = f.read()
                        # Data on disk is encrypted
                        assert actual_data != test_data
                # Case 2
                if case_vault_encrypt is True and case_controller_encrypt is False:
                    # Data if read in Vault context is decrypted
                    loaded_doc = await vault.load(structured_doc.id)
                    stream_to_read_layer2 = await loaded_doc.stream.readable()
                    await stream_to_read_layer2.open()
                    try:
                        actual_data = await stream_to_read_layer2.read()
                    finally:
                        await stream_to_read_layer2.close()
                    assert actual_data == test_data
                # Case 3
                if case_vault_encrypt is False and case_controller_encrypt is True:
                    # Doc controller has access to document content
                    loaded_doc = await vault.load(structured_doc.id)
                    stream_to_read_layer2 = await loaded_doc.stream.readable(
                        jwe_layer2,
                        keys=KeyPair(controller_pk, controller_sk)
                    )
                    await stream_to_read_layer2.open()
                    try:
                        actual_data = await stream_to_read_layer2.read()
                    finally:
                        await stream_to_read_layer2.close()
                    assert actual_data == test_data
                # Case 4
                if case_vault_encrypt is True and case_controller_encrypt is True:
                    # Vault side don/t have access to data
                    loaded_doc = await vault.load(structured_doc.id)
                    stream_to_read_layer2 = await loaded_doc.stream.readable(
                        jwe_layer2,
                        keys=KeyPair(controller_pk, controller_sk)
                    )
                    await stream_to_read_layer2.open()
                    try:
                        actual_data = await stream_to_read_layer2.read()
                    finally:
                        await stream_to_read_layer2.close()
                    assert actual_data == test_data

                await vault.close()
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_data_vault_state_machines_for_docs(config_a: dict, config_b: dict):
    vault_cfg = config_a
    controller_cfg = config_b
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    caller = await get_pairwise3(me=controller_cfg, their=vault_cfg)
    called = await get_pairwise3(me=vault_cfg, their=controller_cfg)
    os.mkdir(dir_under_test)
    try:
        auth = ConfidentialStorageAuthProvider()
        await auth.authorize(called)
        # Init and configure Vault
        vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)

        async def run_vault():
            sm = CalledEncryptedDataVault(called, proxy_to=[vault])
            async with sirius_sdk.context(**vault_cfg):
                async for e in (await sirius_sdk.subscribe()):
                    assert e.pairwise.their.did == called.their.did
                    assert isinstance(e.message, BaseConfidentialStorageMessage)
                    request: BaseConfidentialStorageMessage = e.message
                    print('')
                    await sm.handle(request)
                    print('')

        async def run_controller():
            async with sirius_sdk.context(**controller_cfg):
                m = CallerEncryptedDataVault(caller)
                print('List all vaults')
                vaults = await m.list_vaults()
                assert vaults
                vault_id = vaults[0].id
                print('Select Vault')
                m.select(vault_id)
                print('Open selected vault')
                await m.open()
                print('Create resources')
                sd1 = await m.create_document(uri=f'my_document.bin', meta={'meta1': 'value-1'}, attr1='attr1')
                assert 'my_document.bin' in sd1.id
                assert sd1.doc is not None and sd1.doc.content == b'' and sd1.doc.encrypted is False
                assert sd1.urn.startswith('urn:uuid:')
                assert sd1.meta['meta1'] == 'value-1'
                assert sd1.indexed[0].attributes == ['attr1']
                print('Update resource metadata')
                await m.update(sd1.id, meta={'meta-x': 'value-x'}, attrx='attrx')
                loaded = await m.load(sd1.id)
                assert loaded.meta['meta-x'] == 'value-x'
                assert loaded.indexed[0].attributes == ['attrx']
                assert loaded.id == sd1.id
                assert loaded.urn == sd1.urn
                print('Chek document save/load/encrypt/decrypt operations')
                # save/load non-encrypted doc
                doc = EncryptedDocument()
                doc.content = 'Test message'
                await m.save_document(sd1.id, doc)
                loaded2 = await m.load(sd1.id)
                assert loaded2.doc.content == 'Test message'
                assert loaded2.doc.encrypted is False
                # save/load encrypted doc
                target_vk = await sirius_sdk.Crypto.create_key()
                enc = EncryptedDocument(target_verkeys=[target_vk])
                enc.content = b'Test message'
                await enc.encrypt()
                print('')
                await m.save_document(sd1.id, enc)
                loaded3 = await m.load(sd1.id)
                assert loaded3.doc.encrypted is True
                await loaded3.doc.decrypt()
                assert loaded3.doc.content == b'Test message'
                # Finish
                await m.close()

        results = await run_coroutines(
            run_vault(),
            run_controller(),
            timeout=5
        )
        assert results
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_data_vault_state_machines_for_streams(config_a: dict, config_b: dict):
    vault_cfg = config_a
    controller_cfg = config_b
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    caller = await get_pairwise3(me=controller_cfg, their=vault_cfg)
    called = await get_pairwise3(me=vault_cfg, their=controller_cfg)
    os.mkdir(dir_under_test)
    try:
        auth = ConfidentialStorageAuthProvider()
        await auth.authorize(called)
        # Init and configure Vault
        vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)

        async def run_vault():
            sm = CalledEncryptedDataVault(called, proxy_to=[vault])
            async with sirius_sdk.context(**vault_cfg):
                async for e in (await sirius_sdk.subscribe()):
                    assert e.pairwise.their.did == called.their.did
                    assert isinstance(e.message, BaseConfidentialStorageMessage)
                    request: BaseConfidentialStorageMessage = e.message
                    print('')
                    await sm.handle(request)
                    print('')

        async def run_controller():
            async with sirius_sdk.context(**controller_cfg):
                m = CallerEncryptedDataVault(caller)
                print('List all vaults')
                vaults = await m.list_vaults()
                assert vaults
                vault_id = vaults[0].id
                print('Select Vault')
                m.select(vault_id)
                print('Open selected vault')
                await m.open()
                print('Create resources')
                sd2 = await m.create_stream(uri=f'my_stream.bin', meta={'meta2': 'value-2'}, attr2='attr2')
                assert 'my_stream.bin' in sd2.id
                assert sd2.urn.startswith('urn:uuid:')
                assert sd2.meta['meta2'] == 'value-2'
                assert sd2.indexed[0].attributes == ['attr2']
                print('Update resource metadata')
                await m.update(sd2.id, meta={'meta-x': 'value-x'}, attrx='attrx')
                loaded = await m.load(sd2.id)
                assert loaded.meta['meta-x'] == 'value-x'
                assert loaded.indexed[0].attributes == ['attrx']
                assert loaded.id == sd2.id
                assert loaded.urn == sd2.urn
                # Open stream and write data
                test_data = b'test-data'
                writable = await m.writable(sd2.id)
                await writable.open()
                await writable.write(test_data)
                await writable.close()
                # Open for reading
                readable = await m.readable(sd2.id)
                await readable.open()
                actual_data = await readable.read()
                await readable.close()
                # Check writen is equal to readen bytes
                assert actual_data == test_data
                # Try again for encrypted
                sd_enc = await m.create_stream(uri=f'my_stream_encoded.bin', meta={'meta2': 'value-2'}, attr2='attr2')
                assert sd_enc.stream is not None
                sd_enc = await m.load(sd_enc.id)
                assert sd_enc.stream is not None
                target_vk = await sirius_sdk.Crypto.create_key()
                enc = StreamEncryption().setup(target_verkeys=[target_vk])
                writable_enc = await sd_enc.stream.writable(enc.jwe)
                # !!!! Wrapper encoder JWE will be refreshed !!!!
                wrapper_jwe = writable_enc.enc.jwe
                # !!!!!!!!!!
                await writable_enc.open()
                await writable_enc.write(test_data)
                await writable_enc.close()
                readable_enc = await sd_enc.stream.readable(wrapper_jwe)
                await readable_enc.open()
                actual_data = await readable_enc.read()
                await readable_enc.close()
                assert actual_data == test_data
                # Finish
                await m.close()

        results = await run_coroutines(
            run_vault(),
            run_controller(),
            timeout=5
        )
        assert results
        assert vault.is_open is False
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_data_vault_state_machines_remove_and_indexes(config_a: dict, config_b: dict):
    vault_cfg = config_a
    controller_cfg = config_b
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    caller = await get_pairwise3(me=controller_cfg, their=vault_cfg)
    called = await get_pairwise3(me=vault_cfg, their=controller_cfg)
    os.mkdir(dir_under_test)
    try:
        auth = ConfidentialStorageAuthProvider()
        await auth.authorize(called)
        # Init and configure Vault
        vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)

        async def run_vault():
            sm = CalledEncryptedDataVault(called, proxy_to=[vault])
            async with sirius_sdk.context(**vault_cfg):
                async for e in (await sirius_sdk.subscribe()):
                    assert e.pairwise.their.did == called.their.did
                    assert isinstance(e.message, BaseConfidentialStorageMessage)
                    request: BaseConfidentialStorageMessage = e.message
                    print('')
                    await sm.handle(request)
                    print('')

        async def run_controller():
            async with sirius_sdk.context(**controller_cfg):
                m = CallerEncryptedDataVault(caller)
                print('List all vaults')
                vaults = await m.list_vaults()
                assert vaults
                vault_id = vaults[0].id
                print('Select Vault')
                m.select(vault_id)
                print('Open selected vault')
                await m.open()
                print('Create resources')
                sd1 = await m.create_document('my_document.bin', meta={}, attr1='attr1')
                sd2 = await m.create_stream('my_stream.bin', meta={}, attr1='attr1', attr2='attr2')
                print('Index')
                index = await m.indexes()
                docs1 = await index.filter(attr1='attr1')
                assert len(docs1) == 2
                docs2 = await index.filter(attr1='attr1', attr2='attr2')
                assert len(docs2) == 1
                print('Remove one of resources')
                await m.remove(sd1.id)
                docs3 = await index.filter(attr1='attr1')
                assert len(docs3) == 1
                # Remove by uid
                await m.remove(sd2.urn)
                docs4 = await index.filter(attr1='attr1')
                assert len(docs4) == 0
                # Finish
                await m.close()

        results = await run_coroutines(
            run_vault(),
            run_controller(),
            timeout=5
        )
        assert results
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_data_vault_state_machines_raise_errors(config_a: dict, config_b: dict):
    vault_cfg = config_a
    controller_cfg = config_b
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    caller = await get_pairwise3(me=controller_cfg, their=vault_cfg)
    called = await get_pairwise3(me=vault_cfg, their=controller_cfg)
    os.mkdir(dir_under_test)
    try:
        auth = ConfidentialStorageAuthProvider()
        await auth.authorize(called)
        # Init and configure Vault
        vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)

        async def run_vault():
            sm = CalledEncryptedDataVault(called, proxy_to=[vault])
            async with sirius_sdk.context(**vault_cfg):
                async for e in (await sirius_sdk.subscribe()):
                    assert e.pairwise.their.did == called.their.did
                    assert isinstance(e.message, BaseConfidentialStorageMessage)
                    request: BaseConfidentialStorageMessage = e.message
                    print('')
                    await sm.handle(request)
                    print('')

        async def run_controller():
            async with sirius_sdk.context(**controller_cfg):
                m = CallerEncryptedDataVault(caller)
                print('List all vaults')
                vaults = await m.list_vaults()
                assert vaults
                vault_id = vaults[0].id
                print('Select Vault')
                m.select(vault_id)
                print('Open selected vault')
                await m.open()
                print('#1 Create resource twice')
                await m.create_document('my_document.bin')
                with pytest.raises(DataVaultCreateResourceError):
                    await m.create_document('my_document.bin')
                print('#2 operate with missing resource')
                with pytest.raises(DataVaultResourceMissing):
                    await m.update('file:///missing_document.bin', meta={'meta': 'val'})
                # Finish
                await m.close()

        results = await run_coroutines(
            run_vault(),
            run_controller(),
            timeout=5
        )
        assert results
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_data_vault_recipe_scheduler(config_a: dict, config_b: dict):
    vault_cfg = config_a
    controller_cfg = config_b
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    caller = await get_pairwise3(me=controller_cfg, their=vault_cfg)
    called = await get_pairwise3(me=vault_cfg, their=controller_cfg)
    test_data = b'Test Data'
    os.mkdir(dir_under_test)
    try:
        auth = ConfidentialStorageAuthProvider()
        await auth.authorize(called)
        # Init and configure Vault
        vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)

        async def run_vault():
            async with sirius_sdk.context(**vault_cfg):
                await sirius_sdk.recipes.schedule_vaults(p2p=called, vaults=[vault])

        async def run_controller():
            async with sirius_sdk.context(**controller_cfg):
                m = CallerEncryptedDataVault(caller)
                print('List all vaults')
                vaults = await m.list_vaults()
                assert vaults
                vault_id = vaults[0].id
                print('Select Vault')
                m.select(vault_id)
                print('Open selected vault')
                await m.open()
                # operate with stream
                sd = await m.create_stream('my_stream.bin', meta=StreamMeta(content_type="video/mpeg"))
                wo = await sd.stream.writable()
                await wo.open()
                try:
                    await wo.write(test_data)
                finally:
                    await wo.close()
                ro = await sd.stream.readable()
                await ro.open()
                try:
                    actual_data = await ro.read()
                finally:
                    await ro.close()
                assert actual_data == test_data
                # Finish
                await m.close()

        results = await run_coroutines(
            run_vault(),
            run_controller(),
            timeout=5
        )
        assert results
    finally:
        shutil.rmtree(dir_under_test)


@pytest.mark.asyncio
async def test_data_vault_multilevel_encoding_streams(config_a: dict, config_b: dict):
    vault_cfg = config_a
    controller_cfg = config_b
    dir_under_test = os.path.join(tempfile.tempdir, f'test_vaults_{uuid.uuid4().hex}')
    caller = await get_pairwise3(me=controller_cfg, their=vault_cfg)
    called = await get_pairwise3(me=vault_cfg, their=controller_cfg)
    test_data = b'Test Data' * 1024
    os.mkdir(dir_under_test)
    try:
        auth = ConfidentialStorageAuthProvider()
        await auth.authorize(called)
        # Init and configure Vault
        vault = SimpleDataVault(mounted_dir=dir_under_test, auth=auth)
        assert vault.cfg.key_agreement is not None

        async def run_vault():
            async with sirius_sdk.context(**vault_cfg):
                await sirius_sdk.recipes.schedule_vaults(p2p=called, vaults=[vault])

        async def run_controller():
            async with sirius_sdk.context(**controller_cfg):
                m = CallerEncryptedDataVault(caller)
                print('List all vaults')
                vaults = await m.list_vaults()
                assert vaults
                vault_id = vaults[0].id
                print('Select Vault')
                m.select(vault_id)
                print('Open selected vault')
                await m.open()
                # operate with stream
                sd = await m.create_stream('my_stream.bin', meta=StreamMeta(content_type="video/mpeg"))
                # Init encoding
                enc_key = await sirius_sdk.Crypto.create_key()
                encoding = StreamEncryption().setup(target_verkeys=[enc_key])
                jwe = encoding.jwe
                cek = encoding.cek
                jwe_json = jwe.as_json()
                wo = await sd.stream.writable(jwe, cek)
                await wo.open()
                try:
                    await wo.write(test_data)
                finally:
                    await wo.close()
                # Reopen protocol
                await m.close()
                await m.open()
                # Test reading
                jwe = JWE()
                jwe.from_json(jwe_json)
                ro = await sd.stream.readable(jwe)
                await ro.open()
                try:
                    try:
                        actual_data = await ro.read()
                    except Exception as e:
                        raise e
                finally:
                    await ro.close()
                assert actual_data == test_data
                # Finish
                await m.close()

        results = await run_coroutines(
            run_vault(),
            run_controller(),
            timeout=5
        )
        assert results
    finally:
        shutil.rmtree(dir_under_test)
