import json

import pytest

from sirius_sdk.encryption import create_keypair, pack_message, unpack_message, bytes_to_b58, P2PConnection


@pytest.mark.asyncio
def test_sane():
    verkey, sigkey = create_keypair(b'000000000000000000000000000SEED1')
    verkey_recipient = bytes_to_b58(verkey)
    sigkey_recipient = bytes_to_b58(sigkey)
    verkey, sigkey = create_keypair(b'000000000000000000000000000SEED2')
    verkey_sender = bytes_to_b58(verkey)
    sigkey_sender = bytes_to_b58(sigkey)

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
