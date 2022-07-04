import uuid
import asyncio

import pytest

import sirius_sdk
from sirius_sdk.errors.exceptions import SiriusTimeoutIO
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


@pytest.mark.asyncio
async def test_bus_pubsub(mediator_invitation: dict):
    """Check bus operations:
      - subscribe
      - publish
      - unsubscribe

    """

    thid1 = 'thread-' + uuid.uuid4().hex
    thid2 = 'thread-' + uuid.uuid4().hex
    content1 = b'Message-1'
    content2 = b'Message-2'

    async with sirius_sdk.context(crypto=LocalCryptoManager(), did=LocalDIDManager()):
        my_vk = await sirius_sdk.Crypto.create_key()
        session1 = create_mediator_instance(mediator_invitation, my_vk)
        await session1.connect()
        try:
            session2 = create_mediator_instance(mediator_invitation, my_vk)
            await session2.connect()
            try:
                # Subscribe from session-2
                for thid in [thid1, thid2]:
                    ok = await session2.bus.subscribe(thid)
                    assert ok is True
                # Publish from session-1
                for thid, content in [(thid1, content1), (thid2, content2)]:
                    num = await session1.bus.publish(thid, content)
                    assert num > 0
                # Retrieve from session-2
                for n in range(2):
                    event = await session2.bus.get_event(timeout=3)
                    assert event.payload in [content1, content2]
                # Unsubscribe from thread-2
                await session2.bus.unsubscribe(thid1)
                await asyncio.sleep(1)
                # Publish again
                for thid, num_expected in [(thid1, 0), (thid2, 1)]:
                    num = await session1.bus.publish(thid, content)
                    assert num == num_expected
                # Retrieve from session-2
                event = await session2.bus.get_event(timeout=3)
                assert event.payload == content2
                with pytest.raises(SiriusTimeoutIO):
                    await session2.bus.get_event(timeout=3)
            finally:
                await session2.disconnect()
        finally:
            await session1.disconnect()
