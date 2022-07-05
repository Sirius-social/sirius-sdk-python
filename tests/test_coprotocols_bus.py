import uuid
import asyncio

import pytest

import sirius_sdk
from sirius_sdk import Agent
import sirius_sdk.hub.coprotocols_bus
from sirius_sdk import TheirEndpoint, Pairwise
from sirius_sdk.base import Message
from .conftest import get_pairwise
from .helpers import run_coroutines
from .helpers import ServerTestSuite


TEST_MSG_TYPES = [
    'https://didcomm.org//test_protocol/1.0/request-1',
    'https://didcomm.org/test_protocol/1.0/response-1',
    'https://didcomm.org/test_protocol/1.0/request-2',
    'https://didcomm.org/test_protocol/1.0/response-2',
]
MSG_LOG = []


async def routine1_on_hub(
        co: sirius_sdk.hub.coprotocols_bus.AbstractP2PCoProtocol,
        server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection,
        **kwargs
):
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
        MSG_LOG.append(resp1)
        ok, resp2 = await co.switch(
            message=Message({
                '@type': TEST_MSG_TYPES[2],
                'content': 'Request2'
            })
        )
        assert ok is True
        MSG_LOG.append(resp2)


async def routine2_on_hub(
        co: sirius_sdk.hub.coprotocols_bus.AbstractP2PCoProtocol,
        server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection,
        **kwargs
):
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
    co1 = sirius_sdk.hub.coprotocols_bus.CoProtocolP2PAnon(entity1['verkey'], their1, ['test_protocol'])
    co2 = sirius_sdk.hub.coprotocols_bus.CoProtocolP2PAnon(entity2['verkey'], their2, ['test_protocol'])
    MSG_LOG.clear()
    await run_coroutines(
        routine1_on_hub(co1, **agent1_params),
        routine2_on_hub(co2, **agent2_params),
        timeout=5
    )
    check_msg_log()


@pytest.mark.asyncio
async def test__pairwise_coprotocol(test_suite: ServerTestSuite):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')

    async with sirius_sdk.context(**agent1_params):
        # Get endpoints
        agent1_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
        # Init pairwise list #1
        did1, verkey1 = await sirius_sdk.DID.create_and_store_my_did()

    async with sirius_sdk.context(**agent2_params):
        # Get endpoints
        agent2_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
        # Init pairwise list #1
        did2, verkey2 = await sirius_sdk.DID.create_and_store_my_did()

    async with sirius_sdk.context(**agent1_params):
        await sirius_sdk.DID.store_their_did(did2, verkey2)
    async with sirius_sdk.context(**agent2_params):
        await sirius_sdk.DID.store_their_did(did1, verkey1)

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

    co1 = sirius_sdk.hub.coprotocols_bus.CoProtocolP2P(pairwise1, ['test_protocol'])
    co2 = sirius_sdk.hub.coprotocols_bus.CoProtocolP2P(pairwise2, ['test_protocol'])
    MSG_LOG.clear()
    await run_coroutines(
        routine1_on_hub(co1, **agent1_params),
        routine2_on_hub(co2, **agent2_params)
    )
    check_msg_log()


@pytest.mark.asyncio
async def test__threadbased_protocol_on_hub(test_suite: ServerTestSuite):
    agent1_params = test_suite.get_agent_params('agent1')
    agent2_params = test_suite.get_agent_params('agent2')

    async with sirius_sdk.context(**agent1_params):
        # Get endpoints
        agent1_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
        # Init pairwise list #1
        did1, verkey1 = await sirius_sdk.DID.create_and_store_my_did()

    async with sirius_sdk.context(**agent2_params):
        # Get endpoints
        agent2_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
        # Init pairwise list #1
        did2, verkey2 = await sirius_sdk.DID.create_and_store_my_did()

    async with sirius_sdk.context(**agent1_params):
        await sirius_sdk.DID.store_their_did(did2, verkey2)
    async with sirius_sdk.context(**agent2_params):
        await sirius_sdk.DID.store_their_did(did1, verkey1)

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
    co1 = sirius_sdk.hub.coprotocols_bus.CoProtocolThreadedP2P(thread_id, pairwise1)
    co2 = sirius_sdk.hub.coprotocols_bus.CoProtocolThreadedP2P(thread_id, pairwise2)
    MSG_LOG.clear()
    await run_coroutines(
        routine1_on_hub(co1, **agent1_params),
        routine2_on_hub(co2, **agent2_params),
        timeout=30
    )
    check_msg_log()
