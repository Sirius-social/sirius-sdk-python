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
            p2p=params['p2p']
        )
        await agent.open()
        try:
            success = await agent.ping()
            assert success is True, 'agent [%s] is not pingable' % name
        finally:
            await agent.close()
