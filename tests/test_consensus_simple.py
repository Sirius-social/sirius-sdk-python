import pytest

from sirius_sdk import Agent
from sirius_sdk.agent.microledgers import Transaction
from sirius_sdk.agent.consensus.simple.messages import InitRequestLedgerMessage, InitResponseLedgerMessage

from .conftest import get_pairwise
from .helpers import run_coroutines


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
        request = InitRequestLedgerMessage(
            participants=[A2B.me.did, B2A.me.did],
            ledger_name=ledger_name,
            genesis=genesis_txns,
            root_hash='xxx'
        )

        await request.add_signature(A.wallet.crypto, A2B.me)
        await request.add_signature(B.wallet.crypto, B2A.me)

        assert len(request.signatures) == 2

        await request.check_signatures(A.wallet.crypto, A2B.me.did)
        await request.check_signatures(A.wallet.crypto, B2A.me.did)
        await request.check_signatures(A.wallet.crypto)
        await request.check_signatures(B.wallet.crypto, A2B.me.did)
        await request.check_signatures(B.wallet.crypto, B2A.me.did)
        await request.check_signatures(B.wallet.crypto)

        response = InitResponseLedgerMessage()
        response.assign_from(request)

        payload1 = dict(**request)
        payload2 = dict(**response)
        assert payload1 != payload2

        del payload1['@id']
        del payload1['@type']
        del payload2['@id']
        del payload2['@type']
        assert payload1 == payload2
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
        assert 1, 'TODO'
    finally:
        await A.close()
        await B.close()
        await C.close()
