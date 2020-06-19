import json

import pytest

from sirius_sdk import Agent
from .helpers import ServerTestSuite


@pytest.mark.asyncio
async def test__all_agents_ping(test_suite: ServerTestSuite):
    for name in ['agent1', 'agent2', 'agent3', 'agent4']:
        params = test_suite.get_agent_params(name)
        agent = Agent(
            server_address=params['server_address'],
            credentials=params['credentials'],
            p2p=params['p2p'],
            timeout=5
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
        timeout=5
    )
    await agent.open()
    try:
        # Check wallet calls is ok
        did, verkey = await agent.wallet.did.create_and_store_my_did()
        assert did
        assert verkey
    finally:
        await agent.close()
