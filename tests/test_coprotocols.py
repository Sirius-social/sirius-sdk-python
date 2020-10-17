import uuid
import asyncio

import pytest

import sirius_sdk
from sirius_sdk import Agent
from sirius_sdk.agent.coprotocols import *
from .conftest import get_pairwise
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


async def routine1_on_hub(
        co: sirius_sdk.AbstractP2PCoProtocol,
        server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection,
        **kwargs
):
    async with sirius_sdk.context(server_uri=server_address, credentials=credentials, p2p=p2p):
        first_req = Message({
            '@type': TEST_MSG_TYPES[0],
            'content': 'Request1'
        })
        MSG_LOG.append(first_req)
        ok, resp1 = await co.switch(message=first_req)
        assert ok is True
        MSG_LOG.append(resp1)
        ok, resp2 = await co.switch(
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


async def routine2_on_hub(
        co: sirius_sdk.AbstractP2PCoProtocol,
        server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection,
        **kwargs
):
    async with sirius_sdk.context(server_uri=server_address, credentials=credentials, p2p=p2p):
        await asyncio.sleep(1)
        ok, resp1 = await co.switch(
            message=Message({
                '@type': TEST_MSG_TYPES[1],
                'content': 'Response1'
            })
        )
        assert ok is True
        MSG_LOG.append(resp1)
        await co.send(
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
async def test__their_endpoint_protocol_on_hub(test_suite: ServerTestSuite):
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
    finally:
        await agent1.close()
        await agent2.close()
    # FIRE!!!
    their1 = TheirEndpoint(agent2_endpoint, entity2['verkey'])
    their2 = TheirEndpoint(agent1_endpoint, entity1['verkey'])
    co1 = sirius_sdk.CoProtocolP2PAnon(entity1['verkey'], their1, ['test_protocol'])
    co2 = sirius_sdk.CoProtocolP2PAnon(entity2['verkey'], their2, ['test_protocol'])
    MSG_LOG.clear()
    await run_coroutines(
        routine1_on_hub(co1, **agent1_params),
        routine2_on_hub(co2, **agent2_params)
    )
    check_msg_log()


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
async def test__pairwise_protocol_on_hub(test_suite: ServerTestSuite):
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
    finally:
        await agent1.close()
        await agent2.close()

    co1 = sirius_sdk.CoProtocolP2P(pairwise1, ['test_protocol'])
    co2 = sirius_sdk.CoProtocolP2P(pairwise2, ['test_protocol'])
    MSG_LOG.clear()
    await run_coroutines(
        routine1_on_hub(co1, **agent1_params),
        routine2_on_hub(co2, **agent2_params)
    )
    check_msg_log()


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
async def test__threadbased_protocol_on_hub(test_suite: ServerTestSuite):
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
    finally:
        await agent1.close()
        await agent2.close()

    thread_id = uuid.uuid4().hex
    co1 = sirius_sdk.CoProtocolThreadedP2P(thread_id, pairwise1)
    co2 = sirius_sdk.CoProtocolThreadedP2P(thread_id, pairwise2)
    MSG_LOG.clear()
    await run_coroutines(
        routine1_on_hub(co1, **agent1_params),
        routine2_on_hub(co2, **agent2_params)
    )
    check_msg_log()


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


@pytest.mark.asyncio
async def test_coprotocol_abort(test_suite: ServerTestSuite, agent1: Agent, agent2: Agent):
    agent1_params = test_suite.get_agent_params('agent1')
    await agent1.open()
    await agent2.open()
    try:
        pw1 = await get_pairwise(agent1, agent2)
    finally:
        await agent1.close()
        await agent2.close()

    co = sirius_sdk.CoProtocolThreadedP2P(thid=uuid.uuid4().hex, to=pw1)
    exc = None

    async def infinite_reader(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, **kwargs):
        nonlocal co
        nonlocal exc
        try:
            async with sirius_sdk.context(server_address, credentials, p2p):
                while True:
                    msg = await co.get_one()
                    print(str(msg))
        except OperationAbortedManually as e:
            exc = e

    async def delayed_aborter():
        nonlocal co
        await asyncio.sleep(3)
        await co.abort()

    await run_coroutines(
        infinite_reader(**agent1_params),
        delayed_aborter(),
    )
    assert exc is not None
    assert isinstance(exc, OperationAbortedManually)


@pytest.mark.asyncio
async def test_coprotocol_abort_multiple_ops_single_hub(test_suite: ServerTestSuite, agent1: Agent, agent2: Agent):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')
    await agent1.open()
    await agent2.open()
    try:
        pw1 = await get_pairwise(agent1, agent2)
        pw2 = await get_pairwise(agent2, agent1)
    finally:
        await agent1.close()
        await agent2.close()

    co = sirius_sdk.CoProtocolThreadedP2P(thid=uuid.uuid4().hex, to=pw1)
    new_thread_id = 'new-thread-id-' + uuid.uuid4().hex
    msg_log = []

    async def coroutine1(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, **kwargs):
        nonlocal co
        nonlocal pw1
        nonlocal msg_log
        nonlocal new_thread_id
        async with sirius_sdk.context(server_address, credentials, p2p):
            try:
                while True:
                    msg = await co.get_one()
                    print(str(msg))
            except OperationAbortedManually:
                pass

            try:
                new_co_on_same_hub = sirius_sdk.CoProtocolThreadedP2P(thid=new_thread_id, to=pw1)
                msg, _, _ = await new_co_on_same_hub.get_one()
                print('!')
                msg_log.append(msg)
            except Exception as e:
                raise

    async def coroutine2(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, **kwargs):
        nonlocal co
        nonlocal pw1
        nonlocal new_thread_id
        await asyncio.sleep(3)

        await co.abort()

        await asyncio.sleep(3)
        async with sirius_sdk.context(server_address, credentials, p2p):
            try:
                new_co_on_same_hub = sirius_sdk.CoProtocolThreadedP2P(thid=new_thread_id, to=pw2)
                await new_co_on_same_hub.send(
                    sirius_sdk.aries_rfc.Ping(comment='Test Ping')
                )
            except Exception as e:
                raise

    await run_coroutines(
        coroutine1(**agent1_params),
        coroutine2(**agent2_params)
    )
    assert len(msg_log) == 1
    msg = msg_log[0]
    assert isinstance(msg, sirius_sdk.aries_rfc.Ping)
    assert msg.comment == 'Test Ping'


@pytest.mark.asyncio
async def test_coprotocol_threaded_theirs_send(
        test_suite: ServerTestSuite, agent1: Agent, agent2: Agent, agent3: Agent
):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')
    agent3_params = test_suite.get_agent_params('agent3')
    await agent1.open()
    await agent2.open()
    await agent3.open()
    try:
        pw1 = await get_pairwise(agent1, agent2)
        pw2 = await get_pairwise(agent1, agent3)
    finally:
        await agent1.close()
        await agent2.close()
        await agent3.close()

    thread_id = 'thread-id-' + uuid.uuid4().hex
    rcv_messages = []

    async def sender(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, **kwargs):
        nonlocal thread_id
        async with sirius_sdk.context(server_address, credentials, p2p):
            msg = sirius_sdk.aries_rfc.Ping(comment='Test Ping')
            co = sirius_sdk.CoProtocolThreadedTheirs(thread_id, [pw1, pw2])
            await co.send(msg)

    async def reader(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, **kwargs):
        nonlocal rcv_messages
        async with sirius_sdk.context(server_address, credentials, p2p):
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                rcv_messages.append(event.message)
                return

    await run_coroutines(
        sender(**agent1_params),
        reader(**agent2_params),
        reader(**agent3_params)
    )

    assert len(rcv_messages) == 2
    msg1 = rcv_messages[0]
    msg2 = rcv_messages[1]
    for msg in [msg1, msg2]:
        assert isinstance(msg1, sirius_sdk.aries_rfc.Ping)
        assert msg['~thread']['thid'] == thread_id
        assert msg.comment == 'Test Ping'


@pytest.mark.asyncio
async def test_coprotocol_threaded_theirs_switch(
        test_suite: ServerTestSuite, agent1: Agent, agent2: Agent, agent3: Agent
):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')
    agent3_params = test_suite.get_agent_params('agent3')
    await agent1.open()
    await agent2.open()
    await agent3.open()
    try:
        pw1 = await get_pairwise(agent1, agent2)
        pw2 = await get_pairwise(agent1, agent3)
    finally:
        await agent1.close()
        await agent2.close()
        await agent3.close()

    thread_id = 'thread-id-' + uuid.uuid4().hex
    statuses = None

    async def actor(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, **kwargs):
        nonlocal thread_id
        nonlocal statuses
        async with sirius_sdk.context(server_address, credentials, p2p):
            msg = sirius_sdk.aries_rfc.Ping(comment='Test Ping')
            co = sirius_sdk.CoProtocolThreadedTheirs(thread_id, [pw1, pw2])
            statuses = await co.switch(msg)

    async def responder(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, **kwargs):
        async with sirius_sdk.context(server_address, credentials, p2p):
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                thread_id_ = event.message['~thread']['thid']
                pong = sirius_sdk.aries_rfc.Pong(ping_id=thread_id_, comment='PONG')
                await sirius_sdk.send_to(pong, event.pairwise)
                return

    await run_coroutines(
        actor(**agent1_params),
        responder(**agent2_params),
        responder(**agent3_params),
    )

    assert statuses is not None
    assert pw1 in statuses.keys()
    assert pw2 in statuses.keys()
    for pw, stat in statuses.items():
        success, message = stat
        assert success is True
        assert message['comment'] == 'PONG'


@pytest.mark.asyncio
async def test_coprotocol_threaded_theirs_switch_timeout(
        test_suite: ServerTestSuite, agent1: Agent, agent2: Agent, agent3: Agent
):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')
    await agent1.open()
    await agent2.open()
    await agent3.open()
    try:
        pw1 = await get_pairwise(agent1, agent2)
        pw2 = await get_pairwise(agent1, agent3)
    finally:
        await agent1.close()
        await agent2.close()
        await agent3.close()

    ttl = 10
    thread_id = 'thread-id-' + uuid.uuid4().hex
    statuses = None

    async def actor(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, **kwargs):
        nonlocal thread_id
        nonlocal statuses
        nonlocal ttl
        async with sirius_sdk.context(server_address, credentials, p2p):
            msg = sirius_sdk.aries_rfc.Ping(comment='Test Ping')
            co = sirius_sdk.CoProtocolThreadedTheirs(thread_id, [pw1, pw2], time_to_live=ttl)
            statuses = await co.switch(msg)

    async def responder(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, **kwargs):
        async with sirius_sdk.context(server_address, credentials, p2p):
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                thread_id_ = event.message['~thread']['thid']
                pong = sirius_sdk.aries_rfc.Pong(ping_id=thread_id_, comment='PONG')
                await sirius_sdk.send_to(pong, event.pairwise)
                return

    await run_coroutines(
        actor(**agent1_params),
        responder(**agent2_params),
        timeout=2*ttl
    )

    assert statuses is not None
    stat1 = statuses[pw1]
    assert stat1[0] is True
    assert stat1[1]['comment'] == 'PONG'
    stat1 = statuses[pw2]
    assert stat1[0] is False
    assert stat1[1] is None
