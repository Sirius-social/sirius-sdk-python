import uuid
import asyncio

import pytest

import sirius_sdk
from sirius_sdk.errors.exceptions import SiriusTimeoutIO, OperationAbortedManually
from sirius_sdk.abstract.api import APIRouter, APITransport
from sirius_sdk.hub.defaults.default_apis import APIDefault
from sirius_sdk.hub.defaults.default_crypto import DefaultCryptoService
from sirius_sdk.messaging import Message
from tests.conftest import create_mediator_instance
from tests.helpers import LocalCryptoManager, LocalDIDManager


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
async def test_bus(mediator_invitation: dict):
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


@pytest.mark.asyncio
async def test_bus_abort(mediator_invitation: dict):
    async with sirius_sdk.context(crypto=LocalCryptoManager(), did=LocalDIDManager()):
        my_vk = await sirius_sdk.Crypto.create_key()
        session = create_mediator_instance(mediator_invitation, my_vk)
        await session.connect()
        try:
            thid = 'thread-id-' + uuid.uuid4().hex
            ok = await session.bus.subscribe(thid)
            assert ok is True

            async def __abort():
                await asyncio.sleep(1)
                await session.bus.abort()

            asyncio.ensure_future(__abort())
            with pytest.raises(OperationAbortedManually):
                await session.bus.get_event()
        finally:
            await session.disconnect()


@pytest.mark.asyncio
async def test_router_interface_for_wired_messages(mediator_invitation: dict):
    async with sirius_sdk.context(crypto=LocalCryptoManager(), did=LocalDIDManager()):
        my_vk = await sirius_sdk.Crypto.create_key()
        my_vk_for_messaging = await sirius_sdk.Crypto.create_key()
        mediator = create_mediator_instance(mediator_invitation, my_vk)
        await mediator.connect()
        try:
            my_router: APIRouter = mediator
            their_crypto = DefaultCryptoService()
            their_transport: APITransport = APIDefault(their_crypto)
            their_vk = await their_crypto.create_key()

            my_endpoints = await my_router.get_endpoints()
            assert len(my_endpoints) > 0
            my_endpoint = my_endpoints[0]

            listener = await my_router.subscribe()
            message = Message({
                '@id': 'trust-ping-message-' + uuid.uuid4().hex,
                '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping',
                "comment": "Hi. Are you listening?",
            })

            # Send packed message
            await their_transport.send(
                message=message, their_vk=my_vk_for_messaging,
                endpoint=my_endpoint.address, my_vk=their_vk, routing_keys=my_endpoint.routing_keys
            )
            print('#1')
            event = await listener.get_one(timeout=5)
            print('#2')
            assert event.message == message
            assert event.sender_verkey == their_vk
            assert event.recipient_verkey == my_vk_for_messaging
        finally:
            await mediator.disconnect()


@pytest.mark.asyncio
async def test_router_interface_for_json_messages(mediator_invitation: dict):
    async with sirius_sdk.context(crypto=LocalCryptoManager(), did=LocalDIDManager()):
        my_vk = await sirius_sdk.Crypto.create_key()
        mediator = create_mediator_instance(mediator_invitation, my_vk)
        await mediator.connect()
        try:
            my_router: APIRouter = mediator
            their_crypto = DefaultCryptoService()
            their_transport: APITransport = APIDefault(their_crypto)

            my_endpoints = await my_router.get_endpoints()
            assert len(my_endpoints) > 0
            my_endpoint = my_endpoints[0]

            listener = await my_router.subscribe()
            message = Message({
                '@id': 'trust-ping-message-' + uuid.uuid4().hex,
                '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping',
                "comment": "Hi. Are you listening?",
            })

            # Send packed message
            await their_transport.send(
                message=message, their_vk=[],
                endpoint=my_endpoint.address, my_vk=None, routing_keys=None
            )
            print('#1')
            event = await listener.get_one(timeout=5)
            print('#2')
            assert event.message == message
            assert event.sender_verkey is None
            assert event.recipient_verkey is None
        finally:
            await mediator.disconnect()


@pytest.mark.asyncio
async def test_router_and_bus_stream_intersection(mediator_invitation: dict):
    async with sirius_sdk.context(crypto=LocalCryptoManager(), did=LocalDIDManager()):
        my_vk = await sirius_sdk.Crypto.create_key()
        my_vk_for_messaging = await sirius_sdk.Crypto.create_key()
        session1_listener = create_mediator_instance(mediator_invitation, my_vk)
        session2_bus = create_mediator_instance(mediator_invitation, my_vk)
        await session1_listener.connect()
        await session2_bus.connect()
        try:
            their_crypto = DefaultCryptoService()
            their_transport: APITransport = APIDefault(their_crypto)
            their_vk = await their_crypto.create_key()

            my_endpoints = await session1_listener.get_endpoints()
            assert len(my_endpoints) > 0
            my_endpoint = my_endpoints[0]

            # 1. Allocate Listener
            listener = await session1_listener.subscribe()
            message = Message({
                '@id': 'trust-ping-message-' + uuid.uuid4().hex,
                '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping',
                "comment": "Hi. Are you listening?",
            })

            # Check-1: Send packed message to check listener is OK but bus listener ignore message
            await their_transport.send(
                message=message, their_vk=my_vk_for_messaging,
                endpoint=my_endpoint.address, my_vk=their_vk, routing_keys=my_endpoint.routing_keys
            )
            print('#1')
            event_listener = await listener.get_one(timeout=5)
            assert event_listener.message == message
            print('#2')
            with pytest.raises(SiriusTimeoutIO):
                await session2_bus.bus.get_event(timeout=5)
            print('#3')

            # Check-2: Send bus message and check it will be ignored by listener
            thid = 'thid-' + uuid.uuid4().hex
            await session2_bus.bus.subscribe(thid)
            await session2_bus.bus.publish(thid, b'Some-Content')
            print('#4')
            with pytest.raises(SiriusTimeoutIO):
                await listener.get_one(timeout=5)
            print('#5')
        finally:
            await session1_listener.disconnect()
            await session2_bus.disconnect()
