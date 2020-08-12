import pytest

from sirius_sdk import Agent, Pairwise


@pytest.mark.asyncio
async def test_sane(agent1: Agent, agent2: Agent):
    issuer = agent1
    holder = agent2
    await issuer.open()
    await holder.open()
    try:
        pass
    finally:
        await issuer.close()
        await holder.close()
