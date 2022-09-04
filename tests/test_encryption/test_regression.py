import json

from sirius_sdk.encryption import create_keypair, unpack_message, bytes_to_b58, pack_message


def test_android_device_decrypt_fault(regression_seed1: str, regression_data1: bytes):
    pk, sk = create_keypair(regression_seed1.encode())
    pk, sk = bytes_to_b58(pk), bytes_to_b58(sk)
    print('')
    message, sender_vk, recip_vk = unpack_message(
        enc_message=regression_data1,
        my_verkey=pk,
        my_sigkey=sk
    )
    js = json.loads(message)
    assert js['label'] == 'Игорь'
