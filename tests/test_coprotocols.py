import uuid
import asyncio

import pytest

from sirius_sdk import Agent
from sirius_sdk.agent.coprotocols import *
from .helpers import run_coroutines
from .helpers import ServerTestSuite


TEST_MSG_TYPES = [
    'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test_protocol/1.0/request-1',
    'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test_protocol/1.0/response-1',
    'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test_protocol/1.0/request-2',
    'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test_protocol/1.0/response-2',
]
MSG_LOG = []


async def routine1(protocol: AbstractCoProtocolTransport):
    first_req = Message({
        '@type': TEST_MSG_TYPES[0],
        'content': 'Request1'
    })
    MSG_LOG.append(first_req)
    ok, resp1 = await protocol.switch(message=first_req)
    assert ok is True
    MSG_LOG.append(resp1)
    ok, resp2 = await protocol.switch(
        message=Message({
            '@type': TEST_MSG_TYPES[2],
            'content': 'Request2'
        })
    )
    assert ok is True
    MSG_LOG.append(resp2)


async def routine2(protocol: AbstractCoProtocolTransport):
    await asyncio.sleep(1)
    ok, resp1 = await protocol.switch(
        message=Message({
            '@type': TEST_MSG_TYPES[1],
            'content': 'Response1'
        })
    )
    assert ok is True
    MSG_LOG.append(resp1)
    await protocol.send(
        message=Message({
            '@type': TEST_MSG_TYPES[3],
            'content': 'End'
        })
    )


def check_msg_log():
    assert len(MSG_LOG) == len(TEST_MSG_TYPES)
    for i, item in enumerate(TEST_MSG_TYPES):
        assert MSG_LOG[i].type == TEST_MSG_TYPES[i]
    assert MSG_LOG[0]['content'] == 'Request1'
    assert MSG_LOG[1]['content'] == 'Response1'
    assert MSG_LOG[2]['content'] == 'Request2'
    assert MSG_LOG[3]['content'] == 'End'


@pytest.mark.asyncio
async def test__their_endpoint_protocol(test_suite: ServerTestSuite):
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
        # Make protocol instances
        their1 = TheirEndpoint(agent2_endpoint, entity2['verkey'])
        agent1_protocol = await agent1.spawn(entity1['verkey'], their1)
        assert isinstance(agent1_protocol, TheirEndpointCoProtocolTransport)
        their2 = TheirEndpoint(agent1_endpoint, entity1['verkey'])
        agent2_protocol = await agent2.spawn(entity2['verkey'], their2)
        assert isinstance(agent2_protocol, TheirEndpointCoProtocolTransport)
        await agent1_protocol.start(['test_protocol'])
        await agent2_protocol.start(['test_protocol'])
        try:
            MSG_LOG.clear()
            await run_coroutines(routine1(agent1_protocol), routine2(agent2_protocol))
            check_msg_log()
        finally:
            await agent1_protocol.stop()
            await agent2_protocol.stop()
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test__pairwise_protocol(test_suite: ServerTestSuite):
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
        # Get endpoints
        agent1_endpoint = [e for e in agent1.endpoints if e.routing_keys == []][0].address
        agent2_endpoint = [e for e in agent2.endpoints if e.routing_keys == []][0].address
        # Init pairwise list #1
        did1, verkey1 = await agent1.wallet.did.create_and_store_my_did()
        did2, verkey2 = await agent2.wallet.did.create_and_store_my_did()
        await agent1.wallet.did.store_their_did(did2, verkey2)
        await agent1.wallet.pairwise.create_pairwise(
            their_did=did2, my_did=did1
        )
        await agent2.wallet.did.store_their_did(did1, verkey1)
        await agent2.wallet.pairwise.create_pairwise(
            their_did=did1, my_did=did2
        )
        # Init pairwise list #2
        pairwise1 = Pairwise(
            me=Pairwise.Me(
                did=did1,
                verkey=verkey1
            ),
            their=Pairwise.Their(
                did=did2,
                label='Label-2',
                endpoint=agent2_endpoint,
                verkey=verkey2
            )
        )
        pairwise2 = Pairwise(
            me=Pairwise.Me(
                did=did2,
                verkey=verkey2
            ),
            their=Pairwise.Their(
                did=did1,
                label='Label-1',
                endpoint=agent1_endpoint,
                verkey=verkey1
            )
        )

        agent1_protocol = await agent1.spawn(pairwise1)
        agent2_protocol = await agent2.spawn(pairwise2)
        assert isinstance(agent1_protocol, PairwiseCoProtocolTransport)
        assert isinstance(agent2_protocol, PairwiseCoProtocolTransport)

        await agent1_protocol.start(['test_protocol'])
        await agent2_protocol.start(['test_protocol'])
        try:
            MSG_LOG.clear()
            await run_coroutines(routine1(agent1_protocol), routine2(agent2_protocol))
            check_msg_log()
        finally:
            await agent1_protocol.stop()
            await agent2_protocol.stop()
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test__threadbased_protocol(test_suite: ServerTestSuite):
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
        # Get endpoints
        agent1_endpoint = [e for e in agent1.endpoints if e.routing_keys == []][0].address
        agent2_endpoint = [e for e in agent2.endpoints if e.routing_keys == []][0].address
        # Init pairwise list #1
        did1, verkey1 = await agent1.wallet.did.create_and_store_my_did()
        did2, verkey2 = await agent2.wallet.did.create_and_store_my_did()
        await agent1.wallet.did.store_their_did(did2, verkey2)
        await agent1.wallet.pairwise.create_pairwise(
            their_did=did2, my_did=did1
        )
        await agent2.wallet.did.store_their_did(did1, verkey1)
        await agent2.wallet.pairwise.create_pairwise(
            their_did=did1, my_did=did2
        )
        # Init pairwise list #2
        pairwise1 = Pairwise(
            me=Pairwise.Me(
                did=did1,
                verkey=verkey1
            ),
            their=Pairwise.Their(
                did=did2,
                label='Label-2',
                endpoint=agent2_endpoint,
                verkey=verkey2
            )
        )
        pairwise2 = Pairwise(
            me=Pairwise.Me(
                did=did2,
                verkey=verkey2
            ),
            their=Pairwise.Their(
                did=did1,
                label='Label-1',
                endpoint=agent1_endpoint,
                verkey=verkey1
            )
        )

        thread_id = uuid.uuid4().hex
        agent1_protocol = await agent1.spawn(thread_id, pairwise1)
        agent2_protocol = await agent2.spawn(thread_id, pairwise2)
        assert isinstance(agent1_protocol, ThreadBasedCoProtocolTransport)
        assert isinstance(agent2_protocol, ThreadBasedCoProtocolTransport)

        await agent1_protocol.start()
        await agent2_protocol.start()
        try:
            MSG_LOG.clear()
            await run_coroutines(routine1(agent1_protocol), routine2(agent2_protocol))
            check_msg_log()
        finally:
            await agent1_protocol.stop()
            await agent2_protocol.stop()
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test__protocols_intersections(test_suite: ServerTestSuite):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')
    agent1 = Agent(
        server_address=agent1_params['server_address'],
        credentials=agent1_params['credentials'],
        p2p=agent1_params['p2p'],
        timeout=15,
    )
    agent2 = Agent(
        server_address=agent2_params['server_address'],
        credentials=agent2_params['credentials'],
        p2p=agent2_params['p2p'],
        timeout=15,
    )
    await agent1.open()
    await agent2.open()
    try:
        # Get endpoints
        agent1_endpoint = [e for e in agent1.endpoints if e.routing_keys == []][0].address
        agent2_endpoint = [e for e in agent2.endpoints if e.routing_keys == []][0].address
        # Init pairwise list #1
        did1, verkey1 = await agent1.wallet.did.create_and_store_my_did()
        did2, verkey2 = await agent2.wallet.did.create_and_store_my_did()
        await agent1.wallet.did.store_their_did(did2, verkey2)
        await agent1.wallet.pairwise.create_pairwise(
            their_did=did2, my_did=did1
        )
        await agent2.wallet.did.store_their_did(did1, verkey1)
        await agent2.wallet.pairwise.create_pairwise(
            their_did=did1, my_did=did2
        )
        # Init pairwise list #2
        pairwise1 = Pairwise(
            me=Pairwise.Me(
                did=did1,
                verkey=verkey1
            ),
            their=Pairwise.Their(
                did=did2,
                label='Label-2',
                endpoint=agent2_endpoint,
                verkey=verkey2
            )
        )
        pairwise2 = Pairwise(
            me=Pairwise.Me(
                did=did2,
                verkey=verkey2
            ),
            their=Pairwise.Their(
                did=did1,
                label='Label-1',
                endpoint=agent1_endpoint,
                verkey=verkey1
            )
        )

        thread_id = uuid.uuid4().hex
        agent1_protocol_threaded = await agent1.spawn(thread_id, pairwise1)
        agent2_protocol_threaded = await agent2.spawn(thread_id, pairwise2)
        assert isinstance(agent1_protocol_threaded, ThreadBasedCoProtocolTransport)
        assert isinstance(agent2_protocol_threaded, ThreadBasedCoProtocolTransport)
        agent1_protocol_pairwise = await agent1.spawn(pairwise1)
        agent2_protocol_pairwise = await agent2.spawn(pairwise2)
        assert isinstance(agent1_protocol_pairwise, PairwiseCoProtocolTransport)
        assert isinstance(agent2_protocol_pairwise, PairwiseCoProtocolTransport)

        await agent1_protocol_threaded.start(['test_protocol'])
        await agent2_protocol_threaded.start(['test_protocol'])
        await agent1_protocol_pairwise.start(['test_protocol'])
        await agent2_protocol_pairwise.start(['test_protocol'])
        try:
            MSG_LOG.clear()
            await run_coroutines(
                routine1(agent1_protocol_threaded), routine2(agent2_protocol_threaded),
                routine1(agent1_protocol_pairwise), routine2(agent2_protocol_pairwise),
            )
            # collect messages
            threaded_sequence = [msg for msg in MSG_LOG if '~thread' in msg]
            non_threaded_sequence = [msg for msg in MSG_LOG if '~thread' not in msg]
            # threaded messages
            MSG_LOG.clear()
            MSG_LOG.extend(threaded_sequence)
            check_msg_log()
            for msg in threaded_sequence:
                assert msg['~thread']['thid'] == thread_id
            # non-threaded messages
            MSG_LOG.clear()
            MSG_LOG.extend(non_threaded_sequence)
            check_msg_log()
        finally:
            await agent1_protocol_threaded.stop()
            await agent2_protocol_threaded.stop()
            await agent1_protocol_pairwise.stop()
            await agent2_protocol_pairwise.stop()
    finally:
        await agent1.close()
        await agent2.close()
