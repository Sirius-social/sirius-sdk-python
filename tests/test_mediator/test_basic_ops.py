import uuid
import asyncio

import pytest

import sirius_sdk
from sirius_sdk.abstract.listener import AbstractListener
from sirius_sdk.errors.exceptions import SiriusTimeoutIO, OperationAbortedManually
from sirius_sdk.abstract.api import APIRouter, APITransport
from sirius_sdk.hub.defaults.default_apis import APIDefault
from sirius_sdk.hub.defaults.default_crypto import DefaultCryptoService
from sirius_sdk.hub.mediator import Mediator
from sirius_sdk.messaging import Message
from sirius_sdk.agent.aries_rfc.mixins import ThreadMixin
from tests.conftest import create_mediator_instance
from tests.helpers import LocalCryptoManager, LocalDIDManager, run_coroutines


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
async def test_multiple_bus_instance_for_single_connection(mediator_invitation: dict):
    thid = 'thread-' + uuid.uuid4().hex
    content = b'Message-X'

    async with sirius_sdk.context(crypto=LocalCryptoManager(), did=LocalDIDManager()):
        my_vk = await sirius_sdk.Crypto.create_key()
        session = create_mediator_instance(mediator_invitation, my_vk)
        await session.connect()
        try:
            bus1 = await session.spawn_coprotocol()
            bus2 = await session.spawn_coprotocol()
            await bus1.subscribe(thid)
            await bus1.publish(thid, content)
            with pytest.raises(SiriusTimeoutIO):
                await bus2.get_event(timeout=3)
        finally:
            await session.disconnect()


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
                await session.bus.get_event(timeout=5)
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
            await asyncio.sleep(1)
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
            await asyncio.sleep(1)
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
            await asyncio.sleep(1)
            message = Message({
                '@id': 'trust-ping-message-' + uuid.uuid4().hex,
                '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping',
                "comment": "Hi. Are you listening?",
            })

            print('#')
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


@pytest.mark.asyncio
async def test_load_balancer_with_group_id(mediator_invitation: dict):
    group1 = 'group1'
    group2 = 'group2'
    async with sirius_sdk.context(crypto=LocalCryptoManager(), did=LocalDIDManager()):

        my_vk = await sirius_sdk.Crypto.create_key()
        my_vk_for_messaging = await sirius_sdk.Crypto.create_key()
        their_crypto = LocalCryptoManager()
        their_transport: APITransport = APIDefault(their_crypto)
        their_vk = await their_crypto.create_key()

        session1_group1 = create_mediator_instance(mediator_invitation, my_vk)
        session2_group1 = create_mediator_instance(mediator_invitation, my_vk)
        session3_group2 = create_mediator_instance(mediator_invitation, my_vk)
        await session1_group1.connect()
        await session2_group1.connect()
        await session3_group2.connect()
        try:
            my_endpoints = await session1_group1.get_endpoints()
            assert len(my_endpoints) > 0
            my_endpoint = my_endpoints[0]

            async def listen_async(session: Mediator, group: str):
                listener = await session.subscribe(group)
                event = await listener.get_one()
                return event.message, group

            fut1 = asyncio.ensure_future(listen_async(session1_group1, group1))
            fut2 = asyncio.ensure_future(listen_async(session2_group1, group1))
            fut3 = asyncio.ensure_future(listen_async(session3_group2, group2))
            await asyncio.sleep(5)

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

            print('1')
            done, pending = await asyncio.wait(
                [
                    fut1, fut2, fut3
                ],
                timeout=5, return_when=asyncio.ALL_COMPLETED
            )
            print('#1')
            results = [tsk.result() for tsk in list(done)]
            print(repr(results))
            assert len(done) == 2
            assert len(pending) == 1
            assert all([res[0] == message for res in results])
            assert set([res[1] for res in results]) == {group1, group2}
        finally:
            await session1_group1.disconnect()
            await session2_group1.disconnect()
            await session3_group2.disconnect()


@pytest.mark.asyncio
async def test_subscribe_via_hub(mediator_uri: str, mediator_verkey: str):
    crypto1 = LocalCryptoManager()
    crypto2 = LocalCryptoManager()
    income_event = None
    income_events = []
    group_id = f'group-id-' + uuid.uuid4().hex
    msg_under_test = Message({
        '@id': 'trust-ping-message-' + uuid.uuid4().hex,
        '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping',
        "comment": "Hi. Are you listening?",
    })
    my_vk1 = await crypto1.create_key(seed='0' * 32)
    my_vk2 = await crypto2.create_key(seed='1' * 32)
    cfg1 = sirius_sdk.Config().setup_mediator(mediator_uri, my_vk1, mediator_verkey). \
        override_crypto(dependency=crypto1).override_did(dependency=LocalDIDManager())
    cfg2 = sirius_sdk.Config().setup_mediator(mediator_uri, my_vk2, mediator_verkey). \
        override_crypto(dependency=crypto2).override_did(dependency=LocalDIDManager())

    async with sirius_sdk.context(cfg1):
        endpoints = await sirius_sdk.endpoints()
        cfg1_endpoint = endpoints[0].address

    async def listener(cfg):
        nonlocal income_event
        async with sirius_sdk.context(cfg):
            lst = await sirius_sdk.subscribe(group_id)
            async for event in lst:
                income_event = event
                income_events.append(event)
            print('')

    async def sender(cfg):
        await asyncio.sleep(1)
        async with sirius_sdk.context(cfg):
            try:
                await sirius_sdk.send(msg_under_test, my_vk1, cfg1_endpoint, my_vk2)
                return 'success'
            except Exception as e:
                print('Send Err: ' + repr(e))
                raise

    results = await run_coroutines(listener(cfg1), sender(cfg2), timeout=5)
    assert len(results) == 1 and results[0] == 'success'
    assert income_event is not None
    assert income_event.message == msg_under_test


@pytest.mark.asyncio
async def test_coprotocols_ping_pong(mediator_uri: str, mediator_verkey: str):
    """Local manager provide services on recipient-side, so it should use bus to publish threads to non-trusted
       environment on mediator-side
    """
    crypto_manager1 = LocalCryptoManager()
    did_manager1 = LocalDIDManager(crypto=crypto_manager1)
    crypto_manager2 = LocalCryptoManager()
    did_manager2 = LocalDIDManager(crypto=crypto_manager2)
    my_vk1 = await crypto_manager1.create_key()
    my_vk2 = await crypto_manager2.create_key()
    cfg1 = sirius_sdk.Config().setup_mediator(mediator_uri, my_vk1, mediator_verkey). \
        override_crypto(dependency=crypto_manager1).override_did(dependency=did_manager1)
    cfg2 = sirius_sdk.Config().setup_mediator(mediator_uri, my_vk2, mediator_verkey). \
        override_crypto(dependency=crypto_manager2).override_did(dependency=did_manager2)
    thread_id = 'thread-id-' + uuid.uuid4().hex
    test_msg_count = 2

    # Build P2P
    async with sirius_sdk.context(cfg1):
        # Get endpoints
        agent1_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
        # Init pairwise list #1
        did1, verkey1 = await sirius_sdk.DID.create_and_store_my_did()

    async with sirius_sdk.context(cfg2):
        # Get endpoints
        agent2_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
        # Init pairwise list #1
        did2, verkey2 = await sirius_sdk.DID.create_and_store_my_did()

    async with sirius_sdk.context(cfg1):
        await sirius_sdk.DID.store_their_did(did2, verkey2)
    async with sirius_sdk.context(cfg2):
        await sirius_sdk.DID.store_their_did(did1, verkey1)

    # Init pairwise list #2
    p2p1 = sirius_sdk.Pairwise(
        me=sirius_sdk.Pairwise.Me(
            did=did1,
            verkey=verkey1
        ),
        their=sirius_sdk.Pairwise.Their(
            did=did2,
            label='Label-2',
            endpoint=agent2_endpoint,
            verkey=verkey2
        )
    )
    p2p2 = sirius_sdk.Pairwise(
        me=sirius_sdk.Pairwise.Me(
            did=did2,
            verkey=verkey2
        ),
        their=sirius_sdk.Pairwise.Their(
            did=did1,
            label='Label-1',
            endpoint=agent1_endpoint,
            verkey=verkey1
        )
    )

    async def requester(cfg: sirius_sdk.Config, to: sirius_sdk.Pairwise):
        async with sirius_sdk.context(cfg):
            print('%')
            bus = await sirius_sdk.spawn_coprotocol()
            await bus.subscribe(thid=thread_id)
            print('%')
            await asyncio.sleep(1)
            for n in range(test_msg_count):
                print('#')
                req = Message({
                    '@id': 'trust-ping-message-' + uuid.uuid4().hex,
                    '@type': 'https://didcomm.org/trust_ping/1.0/ping',
                    "comment": "Hi. Are you listening?",
                    "counter": n,
                    "done": n == test_msg_count-1
                })
                ThreadMixin.set_thread(req, ThreadMixin.Thread(thid=thread_id))
                print('#')
                await sirius_sdk.send_to(req, to)
                print('#')
                resp = await bus.get_message()
                print('#')
        print('Done')

    async def responder(cfg: sirius_sdk.Config, to: sirius_sdk.Pairwise):
        async with sirius_sdk.context(cfg):
            print('%')
            bus = await sirius_sdk.spawn_coprotocol()
            await bus.subscribe(thid=thread_id)
            print('%')
            await asyncio.sleep(1)
            while True:
                print('#')
                event = await bus.get_message()
                req = event.message
                assert str(req.type) == 'https://didcomm.org/trust_ping/1.0/ping'
                resp = Message({
                    '@id': 'trust-ping-message-' + uuid.uuid4().hex,
                    '@type': 'https://didcomm.org/trust_ping/1.0/ping_response',
                    "counter": req.get('counter')
                })
                ThreadMixin.set_thread(resp, ThreadMixin.Thread(thid=thread_id))
                print('#')
                await sirius_sdk.send_to(resp, to)
                print('#')
                if req['done'] is True:
                    return

    async def decrypting_in_background(cfg: sirius_sdk.Config, label: str = ''):
        async with sirius_sdk.context(cfg):
            print(f'{label}')
            listener = await sirius_sdk.subscribe(f'DECRYPTING-{label}')
            bus = await sirius_sdk.spawn_coprotocol()
            async for e in listener:
                if e.message and isinstance(e.message, Message) and e.jwe:
                    thread = ThreadMixin.get_thread(e.message)
                    if thread and thread.thid:
                        num = await bus.publish(thread.thid, e.jwe)
                        assert num > 0

    await run_coroutines(
        requester(cfg1, p2p1),
        responder(cfg2, p2p2),
        decrypting_in_background(cfg1, 'Requester'),
        decrypting_in_background(cfg2, 'Responder'),
        timeout=5
    )
