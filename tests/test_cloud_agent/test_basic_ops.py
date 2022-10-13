import asyncio
import uuid

import pytest

import sirius_sdk
from sirius_sdk import Agent
from sirius_sdk.errors.exceptions import SiriusTimeoutIO, OperationAbortedManually
from sirius_sdk.encryption.custom import bytes_to_b58
from sirius_sdk.messaging import Message, register_message_class
from tests.helpers import ServerTestSuite


class TrustPingMessageUnderTest(Message):
    pass


@pytest.mark.asyncio
async def test__all_agents_ping(test_suite: ServerTestSuite):
    for name in ['agent1', 'agent2', 'agent3', 'agent4']:
        params = test_suite.get_agent_params(name)
        agent = Agent(
            server_address=params['server_address'],
            credentials=params['credentials'],
            p2p=params['p2p'],
            timeout=5,
        )
        await agent.open()
        try:
            success = await agent.ping()
            assert success is True, 'agent [%s] is not ping-able' % name
        finally:
            await agent.close()


@pytest.mark.asyncio
async def test_agents_wallet(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent1')
    agent = Agent(
        server_address=params['server_address'],
        credentials=params['credentials'],
        p2p=params['p2p'],
        timeout=5,
    )
    await agent.open()
    try:
        # Check wallet calls is ok
        did, verkey = await agent.wallet.did.create_and_store_my_did()
        assert did
        assert verkey
        # check reopen is OK
        await agent.reopen()
    finally:
        await agent.close()


@pytest.mark.asyncio
async def test_subscribe_with_group_id(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent1')
    agent = Agent(
        server_address=params['server_address'],
        credentials=params['credentials'],
        p2p=params['p2p'],
        timeout=5,
    )
    await agent.open()
    try:
        await agent.subscribe(group_id='test-group')
        group_id = agent.__getattribute__('_Agent__events').balancing_group
        assert group_id == 'test-group'
    finally:
        await agent.close()


@pytest.mark.asyncio
async def test_agents_communications(test_suite: ServerTestSuite):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')
    entity1 = list(agent1_params['entities'].items())[0][1]
    entity2 = list(agent2_params['entities'].items())[0][1]
    agent1 = Agent(
        server_address=agent1_params['server_address'],
        credentials=agent1_params['credentials'],
        p2p=agent1_params['p2p'],
        timeout=5,
    )
    agent2 = Agent(
        server_address=agent2_params['server_address'],
        credentials=agent2_params['credentials'],
        p2p=agent2_params['p2p'],
        timeout=5,
    )
    await agent1.open()
    await agent2.open()
    try:
        # Get endpoints
        agent2_endpoint = [e for e in agent2.endpoints if e.routing_keys == []][0].address
        agent2_listener = await agent2.subscribe()
        # Exchange Pairwise
        await agent1.wallet.did.store_their_did(entity2['did'], entity2['verkey'])
        if not await agent1.wallet.pairwise.is_pairwise_exists(entity2['did']):
            print('#1')
            await agent1.wallet.pairwise.create_pairwise(
                their_did=entity2['did'], my_did=entity1['did']
            )
        await agent2.wallet.did.store_their_did(entity1['did'], entity1['verkey'])
        if not await agent2.wallet.pairwise.is_pairwise_exists(entity1['did']):
            print('#2')
            await agent2.wallet.pairwise.create_pairwise(
                their_did=entity1['did'], my_did=entity2['did']
            )
        # Prepare message
        trust_ping = Message({
            '@id': 'trust-ping-message-' + uuid.uuid4().hex,
            '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping',
            "comment": "Hi. Are you listening?",
            "response_requested": True
        })
        await agent1.send(
            message=trust_ping,
            their_vk=entity2['verkey'],
            endpoint=agent2_endpoint,
            my_vk=entity1['verkey'],
            routing_keys=[]
        )
        event = await agent2_listener.get_one(timeout=5)
        msg = event['message']
        assert msg['@type'] == 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping'
        assert msg['@id'] == trust_ping.id
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_listener_restore_message(test_suite: ServerTestSuite):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')
    entity1 = list(agent1_params['entities'].items())[0][1]
    entity2 = list(agent2_params['entities'].items())[0][1]
    agent1 = Agent(
        server_address=agent1_params['server_address'],
        credentials=agent1_params['credentials'],
        p2p=agent1_params['p2p'],
        timeout=5,
    )
    agent2 = Agent(
        server_address=agent2_params['server_address'],
        credentials=agent2_params['credentials'],
        p2p=agent2_params['p2p'],
        timeout=5,
    )
    await agent1.open()
    await agent2.open()
    try:
        # Get endpoints
        agent2_endpoint = [e for e in agent2.endpoints if e.routing_keys == []][0].address
        agent2_listener = await agent2.subscribe()
        # Exchange Pairwise
        await agent1.wallet.did.store_their_did(entity2['did'], entity2['verkey'])
        if not await agent1.wallet.pairwise.is_pairwise_exists(entity2['did']):
            print('#1')
            await agent1.wallet.pairwise.create_pairwise(
                their_did=entity2['did'], my_did=entity1['did']
            )
        await agent2.wallet.did.store_their_did(entity1['did'], entity1['verkey'])
        if not await agent2.wallet.pairwise.is_pairwise_exists(entity1['did']):
            print('#2')
            await agent2.wallet.pairwise.create_pairwise(
                their_did=entity1['did'], my_did=entity2['did']
            )
        # Bind Message class to protocol
        register_message_class(TrustPingMessageUnderTest, protocol='trust_ping_test')
        # Prepare message
        trust_ping = Message({
            '@id': 'trust-ping-message-' + uuid.uuid4().hex,
            '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping_test/1.0/ping',
            "comment": "Hi. Are you listening?",
            "response_requested": True
        })
        await agent1.send(
            message=trust_ping,
            their_vk=entity2['verkey'],
            endpoint=agent2_endpoint,
            my_vk=entity1['verkey'],
            routing_keys=[]
        )
        event = await agent2_listener.get_one(timeout=5)
        msg = event['message']
        assert isinstance(msg, TrustPingMessageUnderTest), 'Unexpected msg type: ' + str(type(msg))
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_agents_trust_ping(test_suite: ServerTestSuite):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')
    entity1 = list(agent1_params['entities'].items())[0][1]
    entity2 = list(agent2_params['entities'].items())[0][1]
    agent1 = Agent(
        server_address=agent1_params['server_address'],
        credentials=agent1_params['credentials'],
        p2p=agent1_params['p2p'],
        timeout=5,
    )
    agent2 = Agent(
        server_address=agent2_params['server_address'],
        credentials=agent2_params['credentials'],
        p2p=agent2_params['p2p'],
        timeout=5,
    )
    await agent1.open()
    await agent2.open()
    try:
        # Get endpoints
        agent1_endpoint = [e for e in agent1.endpoints if e.routing_keys == []][0].address
        agent2_endpoint = [e for e in agent2.endpoints if e.routing_keys == []][0].address
        agent1_listener = await agent1.subscribe()
        agent2_listener = await agent2.subscribe()
        # Exchange Pairwise
        await agent1.wallet.did.store_their_did(entity2['did'], entity2['verkey'])
        if not await agent1.wallet.pairwise.is_pairwise_exists(entity2['did']):
            print('#1')
            await agent1.wallet.pairwise.create_pairwise(
                their_did=entity2['did'], my_did=entity1['did']
            )
        await agent2.wallet.did.store_their_did(entity1['did'], entity1['verkey'])
        if not await agent2.wallet.pairwise.is_pairwise_exists(entity1['did']):
            print('#2')
            await agent2.wallet.pairwise.create_pairwise(
                their_did=entity1['did'], my_did=entity2['did']
            )
        # Prepare message
        trust_ping = Message({
            '@id': 'trust-ping-message-' + uuid.uuid4().hex,
            '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping',
            "comment": "Hi. Are you listening?",
            "response_requested": True
        })
        await agent1.send(
            message=trust_ping,
            their_vk=entity2['verkey'],
            endpoint=agent2_endpoint,
            my_vk=entity1['verkey'],
            routing_keys=[]
        )
        event = await agent2_listener.get_one(timeout=5)
        assert event['recipient_verkey'] == entity2['verkey']
        assert event['sender_verkey'] == entity1['verkey']
        msg = event['message']
        assert msg['@type'] == 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping'
        assert msg['@id'] == trust_ping.id

        ping_response = Message(
            {
                "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping_response",
                "@id": "e002518b-456e-b3d5-de8e-7a86fe472847",
                "~thread": {"thid": trust_ping.id},
                "comment": "Hi yourself. I'm here."
            }
        )
        await agent2.send(
            message=ping_response,
            their_vk=entity1['verkey'],
            endpoint=agent1_endpoint,
            my_vk=entity2['verkey'],
            routing_keys=[]
        )

        event = await agent1_listener.get_one(timeout=5)
        assert event['recipient_verkey'] == entity1['verkey']
        assert event['sender_verkey'] == entity2['verkey']
        msg = event['message']
        assert msg['@type'] == 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping_response'
        assert msg['@id'] == ping_response.id

    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_agents_crypto(test_suite: ServerTestSuite):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')
    agent1 = Agent(
        server_address=agent1_params['server_address'],
        credentials=agent1_params['credentials'],
        p2p=agent1_params['p2p'],
        timeout=5,
    )
    agent2 = Agent(
        server_address=agent2_params['server_address'],
        credentials=agent2_params['credentials'],
        p2p=agent2_params['p2p'],
        timeout=5,
    )
    await agent1.open()
    await agent2.open()
    try:
        did_signer = 'Th7MpTaRZVRYnPiabds81Y'
        verkey_signer = 'FYmoFw55GeQH7SRFa37dkx1d2dZ3zUF8ckg7wmL7ofN4'
        msg = b'message'
        # 1. Check sign
        signature = await agent1.wallet.crypto.crypto_sign(verkey_signer, msg)
        assert bytes_to_b58(signature) == 'QRHbNQxHLEhBuYKbe3ReTUCNRDnGDYMJvABJFEuUSFU8EzS6orRzWjMf3fR4PSgM2Z5gqfsc1kg6vYpQCCb4bjB'
        # 2. Check verify
        success = await agent2.wallet.crypto.crypto_verify(signer_vk=verkey_signer, msg=msg, signature=signature)
        assert success is True
        # 3. check verify with error
        other_msg = b'other-message'
        success = await agent2.wallet.crypto.crypto_verify(signer_vk=verkey_signer, msg=other_msg, signature=signature)
        assert success is False
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_bus(test_suite: ServerTestSuite):
    agent_params = test_suite.get_agent_params('agent1')
    session1 = Agent(
        server_address=agent_params['server_address'],
        credentials=agent_params['credentials'],
        p2p=agent_params['p2p'],
        timeout=5,
    )
    session2 = Agent(
        server_address=agent_params['server_address'],
        credentials=agent_params['credentials'],
        p2p=agent_params['p2p'],
        timeout=5,
    )
    await session1.open()
    await session2.open()
    try:
        thid1 = 'thread-id-' + uuid.uuid4().hex
        thid2 = 'thread-id-' + uuid.uuid4().hex
        ok = await session1.bus.subscribe(thid1)
        assert ok is True
        ok = await session1.bus.subscribe(thid2)
        assert ok is True

        content = b'Some-Message'
        sub_num = await session2.bus.publish(thid1, content)
        assert sub_num == 1

        event = await session1.bus.get_event(timeout=5)
        assert event.payload == content

        await session1.bus.unsubscribe(thid1)
        await asyncio.sleep(1)

        await session2.bus.publish(thid1, content)
        with pytest.raises(SiriusTimeoutIO):
            await session1.bus.get_event(timeout=3)

        sub_num1 = await session2.bus.publish(thid1, content)
        assert sub_num1 == 0
        sub_num2 = await session2.bus.publish(thid2, content)
        assert sub_num2 == 1
    finally:
        await session1.close()
        await session2.close()


@pytest.mark.asyncio
async def test_bus_abort(test_suite: ServerTestSuite):
    agent_params = test_suite.get_agent_params('agent1')
    session = Agent(
        server_address=agent_params['server_address'],
        credentials=agent_params['credentials'],
        p2p=agent_params['p2p'],
        timeout=5,
    )
    await session.open()
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
        await session.close()


@pytest.mark.asyncio
async def test_bus_for_threaded_protocol(test_suite: ServerTestSuite):
    sender_params = test_suite.get_agent_params('agent1')
    receiver_params = test_suite.get_agent_params('agent2')
    sender_entity = list(sender_params['entities'].items())[0][1]
    receiver_entity = list(receiver_params['entities'].items())[0][1]
    sender = Agent(
        server_address=sender_params['server_address'],
        credentials=sender_params['credentials'],
        p2p=sender_params['p2p'],
        timeout=5,
    )
    receiver = Agent(
        server_address=receiver_params['server_address'],
        credentials=receiver_params['credentials'],
        p2p=receiver_params['p2p'],
        timeout=5,
    )
    await sender.open()
    await receiver.open()
    try:
        # Get endpoints
        receiver_endpoint = [e for e in receiver.endpoints if e.routing_keys == []][0].address
        receiver_listener = await receiver.subscribe()
        # Exchange Pairwise
        # Prepare message
        thid = 'thread-for-ping-' + uuid.uuid4().hex
        trust_ping = Message({
            '@id': 'trust-ping-message-' + uuid.uuid4().hex,
            '@type': 'https://didcomm.org/trust_ping/1.0/ping',
            "comment": "Hi.",
            "~thread": {"thid": thid},
        })
        # Subscribe to events
        ok = await receiver.bus.subscribe(thid)
        assert ok is True
        # Send message
        send_message_kwargs = dict(
            message=trust_ping,
            their_vk=receiver_entity['verkey'],
            endpoint=receiver_endpoint,
            my_vk=sender_entity['verkey'],
            routing_keys=[]
        )
        await sender.send(**send_message_kwargs)
        # Check income
        event = await receiver.bus.get_message(timeout=5)
        assert isinstance(event.message, Message)
        assert event.message.__class__.__name__ == 'Ping'
        assert event.message == trust_ping
        assert event.sender_verkey == sender_entity['verkey']
        assert event.recipient_verkey == receiver_entity['verkey']
        # Unsubscribe
        await receiver.bus.unsubscribe(thid)
        # send again and raise errors on reading
        await sender.send(**send_message_kwargs)
        with pytest.raises(SiriusTimeoutIO):
            await receiver.bus.get_message(timeout=3)
    finally:
        await sender.close()
        await receiver.close()


@pytest.mark.asyncio
async def test_bus_for_complex_protocol(test_suite: ServerTestSuite):
    sender_params = test_suite.get_agent_params('agent1')
    receiver_params = test_suite.get_agent_params('agent2')
    sender_entity = list(sender_params['entities'].items())[0][1]
    receiver_entity = list(receiver_params['entities'].items())[0][1]
    sender = Agent(
        server_address=sender_params['server_address'],
        credentials=sender_params['credentials'],
        p2p=sender_params['p2p'],
        timeout=5,
    )
    receiver = Agent(
        server_address=receiver_params['server_address'],
        credentials=receiver_params['credentials'],
        p2p=receiver_params['p2p'],
        timeout=5,
    )
    await sender.open()
    await receiver.open()
    try:
        # Get endpoints
        receiver_endpoint = [e for e in receiver.endpoints if e.routing_keys == []][0].address
        receiver_listener = await receiver.subscribe()
        # Exchange Pairwise
        # Prepare message
        thid = 'thread-for-ping-' + uuid.uuid4().hex
        trust_ping = Message({
            '@id': 'trust-ping-message-' + uuid.uuid4().hex,
            '@type': 'https://didcomm.org/trust_ping/1.0/ping',
            "comment": "Hi.",
        })
        some_msg = Message({
            '@id': 'some-message-' + uuid.uuid4().hex,
            '@type': 'https://didcomm.org/some-protocol/1.0/some-request',
        })
        sender_vk = sender_entity['verkey']
        receiver_vk = receiver_entity['verkey']
        # Subscribe to events
        ok, binding_ids = await receiver.bus.subscribe_ext(
            sender_vk=[sender_vk], recipient_vk=[receiver_vk], protocols=['trust_ping', 'some-protocol']
        )
        assert ok is True
        # Send message
        send_message_kwargs1 = dict(
            message=trust_ping,
            their_vk=receiver_entity['verkey'],
            endpoint=receiver_endpoint,
            my_vk=sender_entity['verkey'],
            routing_keys=[]
        )
        send_message_kwargs2 = dict(
            message=some_msg,
            their_vk=receiver_entity['verkey'],
            endpoint=receiver_endpoint,
            my_vk=sender_entity['verkey'],
            routing_keys=[]
        )
        # Send messages
        await sender.send(**send_message_kwargs1)
        await sender.send(**send_message_kwargs2)
        # Check income
        event1 = await receiver.bus.get_message(timeout=5)
        event2 = await receiver.bus.get_message(timeout=5)
        if event1.message.__class__.__name__ == 'Ping':
            assert event1.message == trust_ping
            assert event2.message == some_msg
        else:
            assert event1.message == some_msg
            assert event2.message == trust_ping
        # Unsubscribe and try again
        await receiver.bus.unsubscribe_ext(binding_ids)
        # Send messages
        await sender.send(**send_message_kwargs1)
        await sender.send(**send_message_kwargs2)
        with pytest.raises(SiriusTimeoutIO):
            await receiver.bus.get_message(timeout=5)
    finally:
        await sender.close()
        await receiver.close()


@pytest.mark.asyncio
async def test_multiple_bus_instance_for_single_connection(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent1')
    thid = 'test_multiple_bus_instance_for_single_connection-' + uuid.uuid4().hex
    content = b'Message-X'
    async with sirius_sdk.context(params['server_address'], params['credentials'], params['p2p']):
        bus1 = await sirius_sdk.spawn_coprotocol()
        bus2 = await sirius_sdk.spawn_coprotocol()
        await bus1.subscribe(thid)
        await bus1.publish(thid, content)
        with pytest.raises(SiriusTimeoutIO):
            await bus2.get_event(timeout=3)


@pytest.mark.asyncio
async def test_spawn_coprotocol(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent1')
    async with sirius_sdk.context(params['server_address'], params['credentials'], params['p2p']):
        thid = 'thid-' + uuid.uuid4().hex
        bus = await sirius_sdk.spawn_coprotocol()
        ok = await bus.subscribe(thid)
        assert ok is True

        await asyncio.sleep(1)

        payload = b'Content-Under-Test'
        num = await bus.publish(thid, payload)
        assert num > 0

        event = await bus.get_event(timeout=3)
        assert payload == event.payload
