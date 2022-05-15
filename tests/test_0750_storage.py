import os
import json
import uuid

import pytest
import nacl.bindings
import nacl.utils

from sirius_sdk.encryption import create_keypair, pack_message, unpack_message, bytes_to_b58, sign_message, \
    verify_signed_message, did_from_verkey, b58_to_bytes
from sirius_sdk.agent.aries_rfc.feature_0750_storage.components import EncReadOnlyStream, EncWriteOnlyStream, Encryption
from sirius_sdk.agent.aries_rfc.feature_0750_storage import FileSystemReadOnlyStream, FileSystemWriteOnlyStream
from .helpers import calc_file_hash, calc_bytes_hash


@pytest.mark.asyncio
async def test_fs_streams(files_dir: str):
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)
    # 1. Reading All Data
    for chunk_size in [100, 1024, 10000000]:
        ro = FileSystemReadOnlyStream(file_under_test, chunk_size)
        await ro.open()
        try:
            read_data = await ro.read()
            read_data_md5 = calc_bytes_hash(read_data)
            assert read_data_md5 == file_under_test_md5
            assert ro.position == len(read_data)
            assert await ro.eof() is True
        finally:
            await ro.close()
    # 2. Reading with chunks
    for chunk_size in [100, 1024, 10000000]:
        ro = FileSystemReadOnlyStream(file_under_test, chunk_size)
        await ro.open()
        try:
            accum = b''
            async for chunk in ro.read_chunked():
                accum += chunk
            accum_md5 = calc_bytes_hash(read_data)
            assert accum_md5 == file_under_test_md5
            assert ro.position == len(read_data)
            assert await ro.eof() is True
        finally:
            await ro.close()
    # 3. Write stream: create and write all data to file
    wo_file_path = os.path.join(files_dir, 'big_img_writeonly_stream.jpeg')
    for chunk_size in [100, 1024, 10000000]:
        wo = FileSystemWriteOnlyStream(wo_file_path, chunk_size)
        await wo.create(truncate=True)
        try:
            with open(file_under_test, 'rb') as f:
                raw = f.read()
            await wo.open()
            try:
                await wo.write(raw)
                assert wo.position == len(raw)
            finally:
                await wo.close()
            wo_file_md5 = calc_file_hash(wo_file_path)
            assert wo_file_md5 == file_under_test_md5
            assert wo.position == len(raw)
        finally:
            os.remove(wo_file_path)


@pytest.mark.asyncio
async def test_fs_streams_copy(files_dir: str):
    file_under_test = os.path.join(files_dir, 'big_img.jpeg')
    file_under_test_md5 = calc_file_hash(file_under_test)
    # 1. Reading All Data
    for chunk_size in [1024]:
        ro = FileSystemReadOnlyStream(file_under_test, chunk_size)
        await ro.open()
        try:
            wo_file_path = os.path.join(files_dir, 'big_img_copy_stream.jpeg')
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
            assert wo.position == len(raw)
        finally:
            await ro.close()


@pytest.mark.skip
@pytest.mark.asyncio
def test_sane(files_dir: str):
    verkey, sigkey = create_keypair(b'000000000000000000000000000SEED1')
    verkey_recipient = bytes_to_b58(verkey)
    sigkey_recipient = bytes_to_b58(sigkey)
    verkey, sigkey = create_keypair(b'000000000000000000000000000SEED2')
    verkey_sender = bytes_to_b58(verkey)
    sigkey_sender = bytes_to_b58(sigkey)

    img_file = os.path.join(files_dir, 'big_img.jpeg')
    with open(img_file, 'rb') as f:
        content_bin = f.read()

    cek = nacl.bindings.crypto_secretstream_xchacha20poly1305_keygen()
    cek_old = bytes_to_b58(cek)
    target_pk = nacl.bindings.crypto_sign_ed25519_pk_to_curve25519(
        b58_to_bytes(verkey_recipient)
    )
    enc_cek = nacl.bindings.crypto_box_seal(cek, target_pk)
    cek_net = bytes_to_b58(cek)
    output = nacl.bindings.crypto_aead_chacha20poly1305_ietf_encrypt(
        content_bin, aad=b'', nonce=b'000000000000', key=cek
    )

    message = {
        'content': 'Test encryption строка'
    }
    message = json.dumps(message)

    packed = pack_message(
        message=message,
        to_verkeys=[verkey_recipient],
        from_verkey=verkey_sender,
        from_sigkey=sigkey_sender
    )
    unpacked, sender_vk, recip_vk = unpack_message(
        enc_message=packed,
        my_verkey=verkey_recipient,
        my_sigkey=sigkey_recipient
    )
    assert message == unpacked
    assert sender_vk, verkey_sender
    assert recip_vk, verkey_recipient
