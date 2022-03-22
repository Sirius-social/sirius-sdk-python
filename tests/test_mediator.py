import pytest

import sirius_sdk
from .conftest import create_mediator_instance
from .helpers import LocalCryptoManager, LocalDIDManager


@pytest.mark.asyncio
async def test_open_connection(mediator_invitation: dict):
    async with sirius_sdk.context(crypto=LocalCryptoManager(), did=LocalDIDManager()):
        my_vk = await sirius_sdk.Crypto.create_key()
        mediator = create_mediator_instance(mediator_invitation, my_vk)
        await mediator.connect()
        try:
            assert mediator.did_doc is not None
            assert mediator.me.verkey == my_vk
            assert len(mediator.endpoints) == 1
            e = mediator.endpoints[0]
            assert e.routing_keys == []
            assert e.address is not None
            assert e.is_default is True
        finally:
            await mediator.disconnect()


@pytest.mark.asyncio
async def test_routing_keys(mediator_invitation: dict):
    async with sirius_sdk.context(crypto=LocalCryptoManager(), did=LocalDIDManager()):
        my_vk = await sirius_sdk.Crypto.create_key()
        routing_vk = await sirius_sdk.Crypto.create_key()
        mediator = create_mediator_instance(mediator_invitation, my_vk, routing_keys=[routing_vk])
        await mediator.connect()
        try:
            assert len(mediator.endpoints) == 1
            e = mediator.endpoints[0]
            assert len(e.routing_keys) > 0
            assert routing_vk in str(e.routing_keys)
            assert e.address is not None
            assert e.is_default is True
        finally:
            await mediator.disconnect()
