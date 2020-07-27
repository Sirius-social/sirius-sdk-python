import pytest

from sirius_sdk import Agent


@pytest.mark.asyncio
async def test_consensus_1_init_ledger(agent1: Agent, agent2: Agent, agent3: Agent):
    await agent1.open()
    await agent2.open()
    await agent3.open()
    try:
        assert True, 'TODO'
    finally:
        await agent1.close()
        await agent2.close()
        await agent3.close()
