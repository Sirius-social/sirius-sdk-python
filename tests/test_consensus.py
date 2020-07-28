import pytest

from sirius_sdk import Agent

from .conftest import get_pairwise


@pytest.mark.asyncio
async def test_simple_consensus_init_ledger(A: Agent, B: Agent, C: Agent):
    await A.open()
    await B.open()
    await C.open()
    try:
        A2B = await get_pairwise(A, B)
        A2C = await get_pairwise(A, C)
        B2A = await get_pairwise(B, A)
        B2C = await get_pairwise(B, C)
        C2A = await get_pairwise(C, A)
        C2B = await get_pairwise(C, B)
        assert 0, 'TODO'
    finally:
        await A.close()
        await B.close()
        await C.close()
