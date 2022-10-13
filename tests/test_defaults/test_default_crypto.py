import pytest

import pytest

import sirius_sdk
from sirius_sdk.errors.exceptions import SiriusCryptoError
from sirius_sdk.hub.defaults.default_crypto import DefaultCryptoService

from ..helpers import ServerTestSuite


@pytest.mark.asyncio
async def test_sane():
    crypto_under_test = DefaultCryptoService()
    # check key creation
    vk1 = await crypto_under_test.create_key()
    vk2 = await crypto_under_test.create_key()
    assert vk1 != vk2
    seed = '0'*32
    vk3 = await crypto_under_test.create_key(seed)
    vk4 = await crypto_under_test.create_key(seed)
    assert vk3 == vk4
    # Check metadata
    metadata = {'key': 'value'}
    await crypto_under_test.set_key_metadata(vk1, metadata)
    m1 = await crypto_under_test.get_key_metadata(vk1)
    assert m1 == metadata
    m2 = await crypto_under_test.get_key_metadata(vk2)
    assert m2 is None
    # check errors
    unknown_vk = 'A' * 44
    with pytest.raises(SiriusCryptoError):
        await crypto_under_test.get_key_metadata(unknown_vk)


@pytest.mark.asyncio
async def test_pack_messages():
    sender = DefaultCryptoService()
    receiver = DefaultCryptoService()
    vk_sender = await sender.create_key()
    vk_receiver = await receiver.create_key()

    message = 'Test-Message'

    packed = await sender.pack_message(
        message=message, recipient_verkeys=[vk_receiver], sender_verkey=vk_sender
    )
    decrypted = await receiver.unpack_message(packed)
    assert decrypted['message'] == message
    assert decrypted['recipient_verkey'] == vk_receiver
    assert decrypted['sender_verkey'] == vk_sender

    alien_key = 'BntaRZtrnqHE6WYNgJCmcqC3kwwfFrvgXwdTJumywcGc'
    packed = await sender.pack_message(
        message=message, recipient_verkeys=[alien_key], sender_verkey=vk_sender
    )
    with pytest.raises(SiriusCryptoError):
        await receiver.unpack_message(packed)


@pytest.mark.asyncio
async def test_anon_crypt(test_suite: ServerTestSuite):
    cloud = test_suite.get_agent_params('agent1')
    crypto_under_test = DefaultCryptoService()
    recipient_vk = await crypto_under_test.create_key()
    message = b'Test-Message'

    async with sirius_sdk.context(**cloud):
        encrypted = await sirius_sdk.Crypto.anon_crypt(recipient_vk, message)

    decrypted = await crypto_under_test.anon_decrypt(recipient_vk, encrypted)
    assert decrypted == message


@pytest.mark.asyncio
async def test_anon_decrypt(test_suite: ServerTestSuite):
    cloud = test_suite.get_agent_params('agent1')
    crypto_under_test = DefaultCryptoService()
    message = b'Test-Message'

    async with sirius_sdk.context(**cloud):
        recip_vk = await sirius_sdk.Crypto.create_key()

    encrypted = await crypto_under_test.anon_crypt(recip_vk, message)

    async with sirius_sdk.context(**cloud):
        decrypted = await sirius_sdk.Crypto.anon_decrypt(recip_vk, encrypted)

    assert decrypted == message
