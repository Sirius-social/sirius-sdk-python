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


@pytest.mark.asyncio
def test_fixture():
    verkey, sigkey = create_keypair(b'000000000000000000000000000SEED1')
    verkey_recipient = bytes_to_b58(verkey)
    sigkey_recipient = bytes_to_b58(sigkey)
    verkey, sigkey = create_keypair(b'000000000000000000000000000SEED2')
    verkey_sender = bytes_to_b58(verkey)
    packed = b'{"protected": "eyJlbmMiOiAieGNoYWNoYTIwcG9seTEzMDVfaWV0ZiIsICJ0eXAiOiAiSldNLzEuMCIsICJhbGciOiAiQXV0aGNyeXB0IiwgInJlY2lwaWVudHMiOiBbeyJlbmNyeXB0ZWRfa2V5IjogInBKcW1xQS1IVWR6WTNWcFFTb2dySGx4WTgyRnc3Tl84YTFCSmtHU2VMT014VUlwT0RQWTZsMVVsaVVvOXFwS0giLCAiaGVhZGVyIjogeyJraWQiOiAiM1ZxZ2ZUcDZRNFZlRjhLWTdlVHVXRFZBWmFmRDJrVmNpb0R2NzZLR0xtZ0QiLCAic2VuZGVyIjogIjRlYzhBeFRHcWtxamd5NHlVdDF2a0poeWlYZlNUUHo1bTRKQjk1cGZSMG1JVW9KajAwWmswNmUyUEVDdUxJYmRDck8xeTM5LUhGTG5NdW5YQVJZWk5rZ2pyYV8wYTBQODJpbVdNcWNHc1FqaFd0QUhOcUw1OGNkUUYwYz0iLCAiaXYiOiAiVU1PM2o1ZHZwQnFMb2Rvd3V0c244WEMzTkVqSWJLb2oifX1dfQ==", "iv": "MchkHF2M-4hneeUJ", "ciphertext": "UgcdsV-0rIkP25eJuRSROOuqiTEXp4NToKjPMmqqtJs-Ih1b5t3EEbrrHxeSfPsHtlO6J4OqA1jc5uuD3aNssUyLug==", "tag": "sQD8qgJoTrRoyQKPeCSBlQ=="}'
    unpacked, sender_vk, recip_vk = unpack_message(
        enc_message=packed,
        my_verkey=verkey_recipient,
        my_sigkey=sigkey_recipient
    )
    message = json.dumps({
        'content': 'Test encryption строка'
    })
    assert message == unpacked
    assert sender_vk, verkey_sender
    assert recip_vk, verkey_recipient
