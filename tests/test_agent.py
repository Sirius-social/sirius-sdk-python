import uuid

import pytest

from sirius_sdk import Agent
from sirius_sdk.messaging import Message, register_message_class
from .helpers import ServerTestSuite


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
        await agent1.send_message(
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
        await agent1.send_message(
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
        await agent1.send_message(
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
        await agent2.send_message(
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
