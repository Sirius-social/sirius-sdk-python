import uuid
import asyncio

import pytest

import sirius_sdk
import sirius_sdk.hub
from sirius_sdk import Agent, TheirEndpoint, Pairwise
import sirius_sdk.hub.coprotocols
from sirius_sdk.errors.exceptions import *
from sirius_sdk.messaging import Message
from tests.conftest import get_pairwise, get_pairwise3
from tests.helpers import run_coroutines
from tests.helpers import ServerTestSuite

from .helpers import MSG_LOG, check_msg_log, TEST_MSG_TYPES, check_thread_orders


async def routine1(
        co: sirius_sdk.hub.coprotocols.AbstractP2PCoProtocol,
        server_address: str = None, credentials: bytes = None, p2p: sirius_sdk.P2PConnection = None,
        **kwargs
):
    server_address = server_address or kwargs.get('server_uri')
    async with sirius_sdk.context(server_uri=server_address, credentials=credentials, p2p=p2p):
        first_req = Message({
            '@type': TEST_MSG_TYPES[0],
            'content': 'Request1'
        })
        MSG_LOG.append(first_req)
        print('#2')
        ok, resp1 = await co.switch(message=first_req)
        print('#2')
        assert ok is True
        MSG_LOG.append(Message(**resp1))
        ok, resp2 = await co.switch(
            message=Message({
                '@type': TEST_MSG_TYPES[2],
                'content': 'Request2'
            })
        )
        assert ok is True
        MSG_LOG.append(resp2)


async def routine2(
        co: sirius_sdk.hub.coprotocols.AbstractP2PCoProtocol,
        server_address: str = None, credentials: bytes = None, p2p: sirius_sdk.P2PConnection = None,
        **kwargs
):
    server_address = server_address or kwargs.get('server_uri')
    async with sirius_sdk.context(server_uri=server_address, credentials=credentials, p2p=p2p):
        await asyncio.sleep(1)
        print('#1')
        ok, resp1 = await co.switch(
            message=Message({
                '@type': TEST_MSG_TYPES[1],
                'content': 'Response1'
            })
        )
        print('#2')
        assert ok is True
        MSG_LOG.append(Message(**resp1))
        await co.send(
            message=Message({
                '@type': TEST_MSG_TYPES[3],
                'content': 'End'
            })
        )


@pytest.mark.asyncio
async def test__their_endpoint_coprotocol(test_suite: ServerTestSuite):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')
    entity1 = list(agent1_params['entities'].items())[0][1]
    entity2 = list(agent2_params['entities'].items())[0][1]

    async with sirius_sdk.context(**agent1_params):
        agent1_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
    async with sirius_sdk.context(**agent2_params):
        agent2_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address

    # FIRE!!!
    their1 = TheirEndpoint(agent2_endpoint, entity2['verkey'])
    their2 = TheirEndpoint(agent1_endpoint, entity1['verkey'])
    co1 = sirius_sdk.hub.coprotocols.CoProtocolP2PAnon(entity1['verkey'], their1, ['test_protocol'])
    co2 = sirius_sdk.hub.coprotocols.CoProtocolP2PAnon(entity2['verkey'], their2, ['test_protocol'])
    MSG_LOG.clear()
    await run_coroutines(
        routine1(co1, **agent1_params),
        routine2(co2, **agent2_params),
        timeout=5
    )
    check_msg_log()


@pytest.mark.asyncio
async def test__pairwise_coprotocol(config_a: dict, config_b: dict):
    a2b = await get_pairwise3(me=config_a, their=config_b)
    b2a = await get_pairwise3(me=config_b, their=config_a)

    co1 = sirius_sdk.hub.coprotocols.CoProtocolP2P(a2b, ['test_protocol'])
    co2 = sirius_sdk.hub.coprotocols.CoProtocolP2P(b2a, ['test_protocol'])
    MSG_LOG.clear()
    await run_coroutines(
        routine1(co1, **config_a),
        routine2(co2, **config_b)
    )
    check_msg_log()


@pytest.mark.asyncio
async def test__threadbased_coprotocol(config_a: dict, config_b: dict):
    a2b = await get_pairwise3(me=config_a, their=config_b)
    b2a = await get_pairwise3(me=config_b, their=config_a)
    thread_id = uuid.uuid4().hex
    co1 = sirius_sdk.hub.coprotocols.CoProtocolThreadedP2P(thread_id, a2b)
    co2 = sirius_sdk.hub.coprotocols.CoProtocolThreadedP2P(thread_id, b2a)
    MSG_LOG.clear()
    await run_coroutines(
        routine1(co1, **config_a),
        routine2(co2, **config_b),
    )
    check_msg_log()
    check_thread_orders()


@pytest.mark.asyncio
async def test__coprotocols_intersections(config_a: dict, config_b: dict):
    a2b = await get_pairwise3(me=config_a, their=config_b)
    b2a = await get_pairwise3(me=config_b, their=config_a)
    thread_id = uuid.uuid4().hex
    co1_threaded = sirius_sdk.hub.coprotocols.CoProtocolThreadedP2P(thread_id, a2b)
    co2_threaded = sirius_sdk.hub.coprotocols.CoProtocolThreadedP2P(thread_id, b2a)
    co1_p2p = sirius_sdk.hub.coprotocols.CoProtocolP2P(a2b, ['test_protocol'])
    co2_p2p = sirius_sdk.hub.coprotocols.CoProtocolP2P(b2a, ['test_protocol'])
    try:
        MSG_LOG.clear()
        await run_coroutines(
            routine1(co1_threaded, **config_a), routine2(co2_threaded, **config_b),
            routine1(co1_p2p, **config_a), routine2(co2_p2p, **config_b),
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
        await co1_threaded.stop()
        await co2_threaded.stop()
        await co1_p2p.stop()
        await co2_p2p.stop()


@pytest.mark.asyncio
async def test_coprotocol_abort(config_a: dict, config_b: dict):
    a2b = await get_pairwise3(config_a, config_b)
    co = sirius_sdk.hub.coprotocols.CoProtocolThreadedP2P(thid=uuid.uuid4().hex, to=a2b, time_to_live=100)
    assert co.is_alive is False
    assert co.is_aborted is False
    exc = None

    async def infinite_reader(**kwargs):
        nonlocal co
        nonlocal exc
        try:
            async with sirius_sdk.context(**kwargs):
                while True:
                    msg = await co.get_one()
                    print(str(msg))
        except OperationAbortedManually as e:
            exc = e

    async def delayed_aborter():
        nonlocal co
        # Wait for coprotocol will be started implicitly
        await asyncio.sleep(1)
        assert co.is_alive is True
        assert co.is_aborted is False
        await co.abort()

    await run_coroutines(
        infinite_reader(**config_a),
        delayed_aborter(),
    )
    assert exc is not None
    assert isinstance(exc, OperationAbortedManually)
    assert co.is_aborted is True
    assert co.is_alive is False


@pytest.mark.asyncio
async def test_coprotocol_abort_multiple_ops_single_hub(config_a: dict, config_b: dict):
    a2b = await get_pairwise3(config_a, config_b)
    b2a = await get_pairwise3(config_b, config_a)

    co = sirius_sdk.hub.coprotocols.CoProtocolThreadedP2P(thid=uuid.uuid4().hex, to=a2b)
    new_thread_id = 'new-thread-id-' + uuid.uuid4().hex
    msg_log = []

    async def coroutine1(**kwargs):
        nonlocal co
        nonlocal msg_log
        nonlocal new_thread_id
        async with sirius_sdk.context(**kwargs):
            try:
                while True:
                    msg = await co.get_one()
                    print(str(msg))
            except OperationAbortedManually:
                pass

            try:
                new_co_on_same_hub = sirius_sdk.hub.coprotocols.CoProtocolThreadedP2P(thid=new_thread_id, to=a2b)
                msg, _, _ = await new_co_on_same_hub.get_one()
                print('!')
                msg_log.append(msg)
            except Exception as e:
                raise

    async def coroutine2(**kwargs):
        nonlocal co
        nonlocal new_thread_id
        await asyncio.sleep(3)

        await co.abort()

        await asyncio.sleep(3)
        async with sirius_sdk.context(**kwargs):
            try:
                new_co_on_same_hub = sirius_sdk.hub.coprotocols.CoProtocolThreadedP2P(thid=new_thread_id, to=b2a)
                await new_co_on_same_hub.send(
                    sirius_sdk.aries_rfc.Ping(comment='Test Ping')
                )
            except Exception as e:
                raise

    await run_coroutines(
        coroutine1(**config_a),
        coroutine2(**config_b)
    )
    assert len(msg_log) == 1
    msg = msg_log[0]
    assert isinstance(msg, sirius_sdk.aries_rfc.Ping)
    assert msg.comment == 'Test Ping'


@pytest.mark.asyncio
async def test_coprotocol_threaded_theirs_send(config_a: dict, config_b: dict, config_c: dict):
    a2b = await get_pairwise3(config_a, config_b)
    a2c = await get_pairwise3(config_a, config_c)
    thread_id = 'thread-id-' + uuid.uuid4().hex
    rcv_messages = []

    async def sender(**kwargs):
        nonlocal thread_id
        async with sirius_sdk.context(**kwargs):
            msg = sirius_sdk.aries_rfc.Ping(comment='Test Ping')
            co = sirius_sdk.hub.coprotocols.CoProtocolThreadedTheirs(thread_id, [a2b, a2c])
            await co.send(msg)

    async def reader(**kwargs):
        nonlocal rcv_messages
        async with sirius_sdk.context(**kwargs):
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                rcv_messages.append(event.message)
                return

    await run_coroutines(
        sender(**config_a),
        reader(**config_b),
        reader(**config_c)
    )

    assert len(rcv_messages) == 2
    msg1 = rcv_messages[0]
    msg2 = rcv_messages[1]
    for msg in [msg1, msg2]:
        assert isinstance(msg1, sirius_sdk.aries_rfc.Ping)
        assert msg['~thread']['thid'] == thread_id
        assert msg.comment == 'Test Ping'


@pytest.mark.asyncio
async def test_coprotocol_threaded_theirs_switch(config_a: dict, config_b: dict, config_c: dict):
    a2b = await get_pairwise3(config_a, config_b)
    a2c = await get_pairwise3(config_a, config_c)

    thread_id = 'thread-id-' + uuid.uuid4().hex
    statuses = {}

    async def actor(**kwargs):
        nonlocal thread_id
        nonlocal statuses
        async with sirius_sdk.context(**kwargs):
            msg = sirius_sdk.aries_rfc.Ping(comment='Test Ping')
            co = sirius_sdk.hub.coprotocols.CoProtocolThreadedTheirs(thread_id, [a2b, a2c])
            statuses = await co.switch(msg)

    async def responder(**kwargs):
        async with sirius_sdk.context(**kwargs):
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                thread_id_ = event.message['~thread']['thid']
                pong = sirius_sdk.aries_rfc.Pong(ping_id=thread_id_, comment='PONG')
                await sirius_sdk.send_to(pong, event.pairwise)
                return

    await run_coroutines(
        actor(**config_a),
        responder(**config_b),
        responder(**config_c),
    )

    assert statuses is not None
    assert a2b in statuses.keys()
    assert a2c in statuses.keys()
    for pw, stat in statuses.items():
        success, message = stat
        assert success is True
        assert message['comment'] == 'PONG'


@pytest.mark.asyncio
async def test_coprotocol_threaded_theirs_switch_timeout(config_a: dict, config_b: dict, config_c: dict):
    a2b = await get_pairwise3(config_a, config_b)
    a2c = await get_pairwise3(config_a, config_c)
    ttl = 10
    thread_id = 'thread-id-' + uuid.uuid4().hex
    statuses = {}

    async def actor(**kwargs):
        nonlocal thread_id
        nonlocal statuses
        nonlocal ttl
        async with sirius_sdk.context(**kwargs):
            msg = sirius_sdk.aries_rfc.Ping(comment='Test Ping')
            co = sirius_sdk.hub.coprotocols.CoProtocolThreadedTheirs(thread_id, [a2b, a2c], time_to_live=ttl)
            statuses = await co.switch(msg)

    async def responder(**kwargs):
        async with sirius_sdk.context(**kwargs):
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                thread_id_ = event.message['~thread']['thid']
                pong = sirius_sdk.aries_rfc.Pong(ping_id=thread_id_, comment='PONG')
                await sirius_sdk.send_to(pong, event.pairwise)
                return

    await run_coroutines(
        actor(**config_a),
        responder(**config_b),
        timeout=2*ttl
    )

    assert statuses is not None
    stat1 = statuses[a2b]
    assert stat1[0] is True
    assert stat1[1]['comment'] == 'PONG'
    stat1 = statuses[a2c]
    assert stat1[0] is False
    assert stat1[1] is None


@pytest.mark.asyncio
async def test_coprotocol_timeouts(config_a: dict, config_b: dict):
    timeout = 1
    p2p = await get_pairwise3(me=config_a, their=config_b)

    co_under_test1 = sirius_sdk.hub.coprotocols.CoProtocolThreadedP2P(
        thid=uuid.uuid4().hex, to=p2p, time_to_live=timeout
    )
    co_under_test2 = sirius_sdk.hub.coprotocols.CoProtocolP2PAnon(
        p2p.me.verkey, p2p.their, ['test_protocol'], time_to_live=timeout
    )
    co_under_test3 = sirius_sdk.hub.coprotocols.CoProtocolP2P(
        p2p, ['test_protocol'], time_to_live=timeout
    )
    co_under_test4 = sirius_sdk.hub.coprotocols.CoProtocolThreadedTheirs(
        thid=uuid.uuid4().hex, theirs=[p2p]
    )

    async with sirius_sdk.context(**config_a):
        with pytest.raises(SiriusTimeoutIO):
            for co in [co_under_test1, co_under_test2, co_under_test3, co_under_test4]:
                await co.get_one()
