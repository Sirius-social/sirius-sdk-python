import pytest

from sirius_sdk import Agent
from sirius_sdk.agent.microledgers import Transaction
from sirius_sdk.agent.consensus.simple.messages import InitLedgerMessage

from .conftest import get_pairwise


@pytest.mark.asyncio
async def test_init_ledger_messaging(A: Agent, B: Agent, ledger_name: str):
    await A.open()
    await B.open()
    try:
        A2B = await get_pairwise(A, B)
        B2A = await get_pairwise(B, A)
        A2B.me.did = 'did:peer:' + A2B.me.did
        B2A.me.did = 'did:peer:' + B2A.me.did
        genesis_txns = [
            Transaction({"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"})
        ]
        message = InitLedgerMessage(
            participants=[A2B.me.did, B2A.me.did],
            ledger_name=ledger_name,
            genesis=genesis_txns,
            root_hash='xxx'
        )

        await message.add_signature(A2B.me, A.wallet.crypto)
        await message.add_signature(B2A.me, B.wallet.crypto)
        print('@')
    finally:
        await A.close()
        await B.close()


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
