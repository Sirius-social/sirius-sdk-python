import asyncio

import pytest

import sirius_sdk
from sirius_sdk.hub import _current_hub

from .helpers import ServerTestSuite


@pytest.mark.asyncio
async def test_sane(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent1')
    async with sirius_sdk.context(params['server_address'], params['credentials'], params['p2p']):
        inst1 = _current_hub()
        inst2 = _current_hub()
    assert id(inst1) == id(inst2)

    params1 = test_suite.get_agent_params('agent1')
    params2 = test_suite.get_agent_params('agent2')

    async with sirius_sdk.context(params1['server_address'], params1['credentials'], params1['p2p']):
        ping1 = await sirius_sdk.ping()
        endpoints1 = await sirius_sdk.endpoints()
        my_did_list1 = await sirius_sdk.DID.list_my_dids_with_meta()

    async with sirius_sdk.context(params2['server_address'], params2['credentials'], params2['p2p']):
        ping2 = await sirius_sdk.ping()
        endpoints2 = await sirius_sdk.endpoints()
        my_did_list2 = await sirius_sdk.DID.list_my_dids_with_meta()

    endpoints1 = [e.address for e in endpoints1]
    endpoints2 = [e.address for e in endpoints2]
    my_did_list1 = [d['did'] for d in my_did_list1]
    my_did_list2 = [d['did'] for d in my_did_list2]
    assert ping1 is True
    assert ping2 is True
    assert set(endpoints1) != set(endpoints2)
    assert set(my_did_list1) != set(my_did_list2)


@pytest.mark.asyncio
async def test_aborting(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent1')
    agent1 = None
    agent2 = None
    async with sirius_sdk.context(params['server_address'], params['credentials'], params['p2p']):
        hub = _current_hub()
        async with hub.get_agent_connection_lazy() as agent:
            agent1 = agent
            ok1 = await agent1.ping()
            assert ok1 is True

        await hub.abort()

        async with hub.get_agent_connection_lazy() as agent:
            agent2 = agent
            ok2 = await agent2.ping()
            assert ok2 is True

    assert id(agent1) != id(agent2)
    assert agent1 is not None
    assert agent2 is not None


@pytest.mark.asyncio
async def test_spawn_child_routines(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent1')

    hub_parent = None
    hub_child1 = None
    hub_child2 = None

    async def child1():
        nonlocal hub_child1
        hub_child1 = _current_hub()

    async def child2():
        nonlocal hub_child2
        hub_child2 = _current_hub()

    async def parent():
        nonlocal hub_parent
        hub_parent = _current_hub()
        await child1()
        fut = asyncio.ensure_future(child2())
        await asyncio.wait([fut])

    async with sirius_sdk.context(params['server_address'], params['credentials'], params['p2p']):
        await parent()

    assert id(hub_parent) == id(hub_child1)
    assert id(hub_parent) != id(hub_child2)
    assert id(hub_child1) != id(hub_child2)
