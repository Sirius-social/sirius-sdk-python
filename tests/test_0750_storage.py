import os
import json
import uuid

import pytest
import nacl.bindings
import nacl.utils
import nacl.secret

from sirius_sdk.encryption import create_keypair, pack_message, unpack_message, bytes_to_b58, sign_message, \
    verify_signed_message, did_from_verkey, b58_to_bytes
from sirius_sdk.agent.aries_rfc.feature_0750_storage import FileSystemReadOnlyStream, FileSystemWriteOnlyStream, \
    StreamEncryption, StreamDecryption
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
        ro = FileSystemReadOnlyStream(enc_file_path, chunk_size=2048, enc=read_enc)
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
        ro = FileSystemReadOnlyStream(enc_file_path, chunk_size=2048, enc=read_enc)
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
def test_sane(files_dir: str):
    verkey, sigkey = create_keypair(b'000000000000000000000000000SEED1')
    verkey_recipient = bytes_to_b58(verkey)
    sigkey_recipient = bytes_to_b58(sigkey)
    verkey, sigkey = create_keypair(b'000000000000000000000000000SEED2')
    verkey_sender = bytes_to_b58(verkey)
    sigkey_sender = bytes_to_b58(sigkey)

    # key = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
    # key_b58 = bytes_to_b58(key)
    # print('')

    content_bin = b'TEST-MESSAGE'
    nonce = b'000000000000'
    aad = b'21221214'
    cek1 = nacl.bindings.crypto_secretstream_xchacha20poly1305_keygen()
    target_pk = nacl.bindings.crypto_sign_ed25519_pk_to_curve25519(
        b58_to_bytes(verkey_recipient)
    )
    encrypted = nacl.bindings.crypto_aead_chacha20poly1305_ietf_encrypt(
        content_bin, aad=aad, nonce=nonce, key=cek1
    )

    enc_cek = nacl.bindings.crypto_box_seal(cek1, target_pk)

    my_verkey = b58_to_bytes(verkey_recipient)
    my_sigkey = b58_to_bytes(sigkey_recipient)
    pk = nacl.bindings.crypto_sign_ed25519_pk_to_curve25519(my_verkey)
    sk = nacl.bindings.crypto_sign_ed25519_sk_to_curve25519(my_sigkey)
    cek2 = nacl.bindings.crypto_box_seal_open(enc_cek, pk, sk)
    decrypted = nacl.bindings.crypto_aead_chacha20poly1305_ietf_decrypt(
        ciphertext=encrypted, aad=aad, nonce=nonce, key=cek2
    )
    assert content_bin == decrypted
