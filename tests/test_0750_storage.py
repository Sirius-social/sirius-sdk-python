import asyncio
import math
import os
import json
import uuid

import pytest
import nacl.bindings
import nacl.utils
import nacl.secret

import sirius_sdk
from sirius_sdk.encryption import create_keypair, pack_message, unpack_message, bytes_to_b58, sign_message, \
    verify_signed_message, did_from_verkey, b58_to_bytes
from sirius_sdk.agent.aries_rfc.feature_0750_storage import FileSystemReadOnlyStream, FileSystemWriteOnlyStream, \
    StreamEncryption, StreamDecryption, CallerReadOnlyStreamProtocol, CalledReadOnlyStreamProtocol
from .helpers import calc_file_hash, calc_bytes_hash, calc_file_size, run_coroutines
from .conftest import get_pairwise3


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
            with pytest.raises(EOFError):
                await wo.seek_to_chunk(1000)
            with pytest.raises(EOFError):
                await wo.write_chunk(b'', 1000)
            # Check Reader
            ro = FileSystemReadOnlyStream(file_under_test, chunks_num=len(chunks))
            await ro.open()
            try:
                assert ro.current_chunk == 0
                assert ro.chunks_num == len(chunks)
                for no, expected_chunk in enumerate(chunks):
                    await ro.seek_to_chunk(no)
                    chunk_offset, actual_chunk = await ro.read_chunk(no)
                    assert chunk_offset == no+1
                    assert expected_chunk == actual_chunk
                # Check Reader EOF
                assert await ro.eof() is True
                with pytest.raises(EOFError):
                    await ro.seek_to_chunk(1000)
                with pytest.raises(EOFError):
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

    sender_vk_bytes, sender_sigkey_bytes = create_keypair(b'00000000000000000000000000SENDER')
    sender_vk, sender_sigkey = bytes_to_b58(sender_vk_bytes), bytes_to_b58(sender_sigkey_bytes)
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
            state_machine = CalledReadOnlyStreamProtocol(thid=testing_thid)
            await state_machine.run_forever(called_p2p, stream)

    async def caller():
        async with sirius_sdk.context(**config_c):
            ro = CallerReadOnlyStreamProtocol(called=caller_p2p, uri=file_under_test, thid=testing_thid)
            # open
            await ro.open()
            # checks...
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

    await run_coroutines(called(), caller(), timeout=5)
