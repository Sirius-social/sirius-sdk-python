from typing import List

import pytest

from sirius_sdk import Agent
from sirius_sdk.errors.exceptions import *
from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.agent.microledgers import Transaction
from sirius_sdk.agent.consensus.simple.state_machines import MicroLedgerSimpleConsensus
from sirius_sdk.agent.consensus.simple.messages import InitRequestLedgerMessage, InitResponseLedgerMessage

from .conftest import get_pairwise
from .helpers import run_coroutines


async def routine_of_ledger_creator(
        creator: Agent, me: Pairwise.Me, participants: List[str], ledger_name: str, genesis: List[dict]
):
    machine = MicroLedgerSimpleConsensus(
        creator.wallet.crypto, me, creator.pairwise_list, creator.microledgers, creator
    )
    genesis = [Transaction.create(txn) for txn in genesis]
    try:
        success, ledger = await machine.init_microledger(ledger_name, participants, genesis)
        print('@')
    except Exception as e:
        raise


async def routine_of_ledger_creation_acceptor(acceptor: Agent):
    print('#')
    listener = await acceptor.subscribe()
    print('#')
    try:
        event = await listener.get_one()
        assert event.pairwise is not None
        propose = event.message
        assert isinstance(propose, InitRequestLedgerMessage)
        machine = MicroLedgerSimpleConsensus(
            acceptor.wallet.crypto, event.pairwise.me, acceptor.pairwise_list, acceptor.microledgers, acceptor
        )
        success, ledger = await machine.accept_microledger(event.pairwise, propose)
        print('@')
    except Exception as e:
        raise


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
async def test_simple_consensus_init_ledger(A: Agent, B: Agent, C: Agent, ledger_name: str):
    await A.open()
    await B.open()
    await C.open()
    try:
        A2B = await get_pairwise(A, B)
        A2C = await get_pairwise(A, C)
        assert A2B.me == A2C.me
        B2A = await get_pairwise(B, A)
        B2C = await get_pairwise(B, C)
        assert B2A.me == B2C.me
        C2A = await get_pairwise(C, A)
        C2B = await get_pairwise(C, B)
        assert C2A.me == C2B.me
        participants = [
            A2B.me.did,
            A2B.their.did,
            A2C.their.did
        ]
        genesis = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"},
            {"reqId": 2, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op2"}
        ]
        coro_creator = routine_of_ledger_creator(A, A2B.me, participants, ledger_name, genesis)
        coro_acceptor1 = routine_of_ledger_creation_acceptor(B)
        coro_acceptor2 = routine_of_ledger_creation_acceptor(C)

        await run_coroutines(coro_creator, coro_acceptor1, coro_acceptor2, timeout=1000)

        is_exists_for_A = await A.microledgers.is_exists(ledger_name)
        is_exists_for_B = await B.microledgers.is_exists(ledger_name)
        is_exists_for_C = await C.microledgers.is_exists(ledger_name)
        assert is_exists_for_A
        assert is_exists_for_B
        assert is_exists_for_C
    finally:
        await A.close()
        await B.close()
        await C.close()
