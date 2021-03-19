import copy
from typing import List
from datetime import datetime

import pytest

import sirius_sdk
from sirius_sdk import Agent, P2PConnection
from sirius_sdk.agent.microledgers.abstract import AbstractMicroledger
from sirius_sdk.agent.consensus.simple.state_machines import MicroLedgerSimpleConsensus
from sirius_sdk.agent.consensus.simple.messages import *

from .conftest import get_pairwise
from .helpers import run_coroutines, ServerTestSuite


async def routine_of_ledger_creator(
        uri: str, credentials: bytes, p2p: P2PConnection,
        me: Pairwise.Me, participants: List[str], ledger_name: str, genesis: List[dict]
):
    async with sirius_sdk.context(uri, credentials, p2p):
        machine = MicroLedgerSimpleConsensus(me)
        genesis = [Transaction.create(txn) for txn in genesis]
        success, ledger = await machine.init_microledger(ledger_name, participants, genesis)
        return success, ledger


async def routine_of_ledger_creation_acceptor(uri: str, credentials: bytes, p2p: P2PConnection):
    async with sirius_sdk.context(uri, credentials, p2p):
        listener = await sirius_sdk.subscribe()
        event = await listener.get_one()
        assert event.pairwise is not None
        propose = event.message
        assert isinstance(propose, InitRequestLedgerMessage)
        machine = MicroLedgerSimpleConsensus(event.pairwise.me)
        success, ledger = await machine.accept_microledger(event.pairwise, propose)
        return success, ledger


async def routine_of_txn_committer(
        uri: str, credentials: bytes, p2p: P2PConnection,
        me: Pairwise.Me, participants: List[str],
        ledger: Union[AbstractMicroledger, List[AbstractMicroledger]], txns: List[dict]
):
    async with sirius_sdk.context(uri, credentials, p2p):
        machine = MicroLedgerSimpleConsensus(me)
        txns = [Transaction.create(txn) for txn in txns]
        if isinstance(ledger, AbstractMicroledger):
            success, txns = await machine.commit(ledger, participants, txns)
        else:
            success = await machine.commit_in_parallel(ledger, participants, txns)
        return success, txns


async def routine_of_txn_acceptor(
        uri: str, credentials: bytes, p2p: P2PConnection,
        txns: List[Transaction] = None
):
    async with sirius_sdk.context(uri, credentials, p2p):
        listener = await sirius_sdk.subscribe()
        while True:
            event = await listener.get_one()
            assert event.pairwise is not None
            propose = event.message
            if isinstance(propose, ProposeTransactionsMessage):
                if txns:
                    propose['transactions'] = txns
                machine = MicroLedgerSimpleConsensus(event.pairwise.me)
                success = await machine.accept_commit(event.pairwise, propose)
                return success
            elif isinstance(propose, ProposeParallelTransactionsMessage):
                machine = MicroLedgerSimpleConsensus(event.pairwise.me)
                success = await machine.accept_commit_parallel(event.pairwise, propose)
                return success


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
async def test_transaction_messaging(A: Agent, B: Agent, ledger_name: str):
    await A.open()
    await B.open()
    try:
        a2b = await get_pairwise(A, B)
        b2a = await get_pairwise(B, A)
        a2b.me.did = 'did:peer:' + a2b.me.did
        b2a.me.did = 'did:peer:' + b2a.me.did
        genesis_txns = [
            Transaction({"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"})
        ]
        ledger_for_a, txns = await A.microledgers.create(ledger_name, genesis_txns)
        ledger_for_b, txns = await B.microledgers.create(ledger_name, genesis_txns)

        new_transactions = [
            Transaction({"reqId": 2, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op2"}),
            Transaction({"reqId": 3, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op3"}),
        ]
        pos1, pos2, new_txns = await ledger_for_a.append(new_transactions)
        # A -> B
        state = MicroLedgerState(
                {
                    'name': ledger_for_a.name,
                    'seq_no': ledger_for_a.seq_no,
                    'size': ledger_for_a.size,
                    'uncommitted_size': ledger_for_a.uncommitted_size,
                    'root_hash': ledger_for_a.root_hash,
                    'uncommitted_root_hash': ledger_for_a.uncommitted_root_hash
                }
        )
        x = MicroLedgerState.from_ledger(ledger_for_a)
        assert state == x
        assert state.hash == x.hash
        propose = ProposeTransactionsMessage(
            transactions=new_txns,
            state=state
        )
        propose.validate()
        # B -> A
        await ledger_for_b.append(propose.transactions)
        pre_commit = PreCommitTransactionsMessage(
            state=MicroLedgerState(
                {
                    'name': ledger_for_b.name,
                    'seq_no': ledger_for_b.seq_no,
                    'size': ledger_for_b.size,
                    'uncommitted_size': ledger_for_b.uncommitted_size,
                    'root_hash': ledger_for_b.root_hash,
                    'uncommitted_root_hash': ledger_for_b.uncommitted_root_hash
                }
            )
        )
        await pre_commit.sign_state(B.wallet.crypto, b2a.me)
        pre_commit.validate()
        ok, loaded_state_hash = await pre_commit.verify_state(A.wallet.crypto, a2b.their.verkey)
        assert ok is True
        assert loaded_state_hash == state.hash
        # A -> B
        commit = CommitTransactionsMessage()
        commit.add_pre_commit(a2b.their.did, pre_commit)
        commit.validate()
        states = await commit.verify_pre_commits(A.wallet.crypto, state)
        assert a2b.their.did in str(states)
        assert a2b.their.verkey in str(states)
        # B -> A (post-commit)
        post_commit = PostCommitTransactionsMessage()
        await post_commit.add_commit_sign(B.wallet.crypto, commit, b2a.me)
        post_commit.validate()
        ok = await post_commit.verify_commits(A.wallet.crypto, commit, [a2b.their.verkey])
        assert ok is True
    finally:
        await A.close()
        await B.close()


@pytest.mark.asyncio
async def test_parallel_transactions_messaging(A: Agent, B: Agent, ledger_names: List[str]):
    await A.open()
    await B.open()
    try:
        txn_time = str(datetime.now())
        a2b = await get_pairwise(A, B)
        b2a = await get_pairwise(B, A)
        a2b.me.did = 'did:peer:' + a2b.me.did
        b2a.me.did = 'did:peer:' + b2a.me.did
        genesis_txns = [
            Transaction({"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"})
        ]
        ledgers_for_a = []
        ledgers_for_b = []
        for n in ledger_names:
            ledger_for_a, _ = await A.microledgers.create(n, genesis_txns)
            ledger_for_b, _ = await B.microledgers.create(n, genesis_txns)
            ledgers_for_a.append(ledger_for_a)
            ledgers_for_b.append(ledger_for_b)

        new_transactions = [
            Transaction({"reqId": 2, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op2"}),
            Transaction({"reqId": 3, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op3"}),
        ]
        for txn in new_transactions:
            txn.time = txn_time
        # A -> B
        states_for_a = []
        for ledger_for_a in ledgers_for_a:
            pos1, pos2, new_txns = await ledger_for_a.append(new_transactions)
            state = MicroLedgerState.from_ledger(ledger_for_a)
            states_for_a.append(state)
        propose = ProposeParallelTransactionsMessage(transactions=new_transactions, states=states_for_a)
        propose.validate()
        # B -> A
        states_for_b = []
        for ledger_name in propose.ledgers:
            ledger_for_b = await B.microledgers.ledger(ledger_name)
            pos1, pos2, new_txns = await ledger_for_b.append(propose.transactions)
            states_for_b.append(MicroLedgerState.from_ledger(ledger_for_b))
        pre_commit = PreCommitParallelTransactionsMessage(transactions=new_transactions, states=states_for_b)
        await pre_commit.sign_states(B.wallet.crypto, b2a.me)
        pre_commit.validate()
        ok, state_hash_for_b = await pre_commit.verify_state(A.wallet.crypto, a2b.their.verkey)
        assert ok is True
        assert state_hash_for_b == propose.hash
        # A -> B
        commit = CommitParallelTransactionsMessage()
        commit.add_pre_commit(a2b.their.did, pre_commit)
        commit.validate()
        states = await commit.verify_pre_commits(A.wallet.crypto, propose.hash)
        assert a2b.their.did in str(states)
        assert a2b.their.verkey in str(states)
        # B -> A (post-commit)
        post_commit = PostCommitParallelTransactionsMessage()
        await post_commit.add_commit_sign(B.wallet.crypto, commit, b2a.me)
        post_commit.validate()
        ok = await post_commit.verify_commits(A.wallet.crypto, commit, [a2b.their.verkey])
        assert ok is True
    finally:
        await A.close()
        await B.close()


@pytest.mark.asyncio
async def test_parallel_batching_api_messaging(A: Agent, B: Agent, ledger_names: List[str]):
    txn_time = str(datetime.now())
    await A.open()
    await B.open()
    try:
        a2b = await get_pairwise(A, B)
        b2a = await get_pairwise(B, A)
        a2b.me.did = 'did:peer:' + a2b.me.did
        b2a.me.did = 'did:peer:' + b2a.me.did
        genesis_txns = [
            Transaction({"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"})
        ]

        ledgers_for_a = []
        ledgers_for_b = []
        for n in ledger_names:
            ledger_for_a, _ = await A.microledgers.create(n, genesis_txns)
            ledgers_for_a.append(ledger_for_a)
            ledger_for_b, _ = await B.microledgers.create(n, genesis_txns)
            ledgers_for_b.append(ledger_for_b)

        new_transactions = [
            Transaction({"reqId": 2, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op2"}),
            Transaction({"reqId": 3, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op3"}),
        ]
        for txn in new_transactions:
            txn.time = txn_time

        batching_api_for_a = await A.microledgers.batched()
        batching_api_for_b = await B.microledgers.batched()
        await batching_api_for_a.open(ledger_names)
        await batching_api_for_b.open(ledger_names)
        try:
            # A -> B
            await batching_api_for_a.append(new_transactions)
            propose = ProposeParallelTransactionsMessage(
                transactions=new_transactions,
                states=[MicroLedgerState.from_ledger(item) for item in ledgers_for_a]
            )
            propose.validate()
            # B -> A
            await batching_api_for_b.append(propose.transactions)
            states_for_b = [MicroLedgerState.from_ledger(item) for item in ledgers_for_b]
            pre_commit = PreCommitParallelTransactionsMessage(states=states_for_b)
            await pre_commit.sign_states(B.wallet.crypto, b2a.me)
            pre_commit.validate()
            ok, state_hash_for_b = await pre_commit.verify_state(A.wallet.crypto, a2b.their.verkey)
            assert ok is True
            assert state_hash_for_b == propose.hash
            # A -> B
            commit = CommitParallelTransactionsMessage()
            commit.add_pre_commit(a2b.their.did, pre_commit)
            commit.validate()
            states = await commit.verify_pre_commits(A.wallet.crypto, propose.hash)
            assert a2b.their.did in str(states)
            assert a2b.their.verkey in str(states)
            # B -> A (post-commit)
            post_commit = PostCommitParallelTransactionsMessage()
            await post_commit.add_commit_sign(B.wallet.crypto, commit, b2a.me)
            post_commit.validate()
            ok = await post_commit.verify_commits(A.wallet.crypto, commit, [a2b.their.verkey])
            assert ok is True
        finally:
            await batching_api_for_a.close()
            await batching_api_for_b.close()
    finally:
        await A.close()
        await B.close()


@pytest.mark.asyncio
async def test_simple_consensus_init_ledger(
        A: Agent, B: Agent, C: Agent, ledger_name: str, test_suite: ServerTestSuite
):
    A_params = test_suite.get_agent_params('agent1')
    B_params = test_suite.get_agent_params('agent2')
    C_params = test_suite.get_agent_params('agent3')
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
        coro_creator = routine_of_ledger_creator(
            A_params['server_address'], A_params['credentials'], A_params['p2p'],
            A2B.me, participants, ledger_name, genesis
        )
        coro_acceptor1 = routine_of_ledger_creation_acceptor(
            B_params['server_address'], B_params['credentials'], B_params['p2p'],
        )
        coro_acceptor2 = routine_of_ledger_creation_acceptor(
            C_params['server_address'], C_params['credentials'], C_params['p2p'],
        )

        stamp1 = datetime.now()
        print('> begin')
        await run_coroutines(coro_creator, coro_acceptor1, coro_acceptor2, timeout=30)
        print('> end')
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        print(f'***** Consensus timeout: {delta.seconds}')

        is_exists_for_A = await A.microledgers.is_exists(ledger_name)
        is_exists_for_B = await B.microledgers.is_exists(ledger_name)
        is_exists_for_C = await C.microledgers.is_exists(ledger_name)
        assert is_exists_for_A
        assert is_exists_for_B
        assert is_exists_for_C

        for agent in [A, B, C]:
            ledger = await agent.microledgers.ledger(ledger_name)
            txns = await ledger.get_all_transactions()
            assert len(txns) == 2
            assert 'op1' in str(txns)
            assert 'op2' in str(txns)
    finally:
        await A.close()
        await B.close()
        await C.close()


@pytest.mark.asyncio
async def test_simple_consensus_commit(
        A: Agent, B: Agent, C: Agent, ledger_name: str, test_suite: ServerTestSuite
):
    A_params = test_suite.get_agent_params('agent1')
    B_params = test_suite.get_agent_params('agent2')
    C_params = test_suite.get_agent_params('agent3')
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
        ledger_for_a, _ = await A.microledgers.create(ledger_name, genesis)
        await B.microledgers.create(ledger_name, genesis)
        await C.microledgers.create(ledger_name, genesis)

        txns = [
            {"reqId": 3, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op3"},
            {"reqId": 4, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op4"},
            {"reqId": 5, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op5"},
        ]

        coro_committer = routine_of_txn_committer(
            A_params['server_address'], A_params['credentials'], A_params['p2p'],
            A2B.me, participants, ledger_for_a, txns
        )
        coro_acceptor1 = routine_of_txn_acceptor(
            B_params['server_address'], B_params['credentials'], B_params['p2p'],
        )
        coro_acceptor2 = routine_of_txn_acceptor(
            C_params['server_address'], C_params['credentials'], C_params['p2p'],
        )

        stamp1 = datetime.now()
        print('> begin')
        await run_coroutines(coro_committer, coro_acceptor1, coro_acceptor2, timeout=60)
        print('> end')
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        print(f'***** Consensus timeout: {delta.seconds}')

        ledger_for_a = await A.microledgers.ledger(ledger_name)
        ledger_for_b = await B.microledgers.ledger(ledger_name)
        ledger_for_c = await C.microledgers.ledger(ledger_name)
        for ledger in [ledger_for_a, ledger_for_b, ledger_for_c]:
            all_txns = await ledger.get_all_transactions()
            assert 'op3' in str(all_txns)
            assert 'op4' in str(all_txns)
            assert 'op5' in str(all_txns)
    finally:
        await A.close()
        await B.close()
        await C.close()


@pytest.mark.asyncio
async def test_simple_consensus_commit_parallel(
        A: Agent, B: Agent, C: Agent, ledger_names: List[str], test_suite: ServerTestSuite
):
    A_params = test_suite.get_agent_params('agent1')
    B_params = test_suite.get_agent_params('agent2')
    C_params = test_suite.get_agent_params('agent3')
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
        txns = [
            {"reqId": 3, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op3"},
            {"reqId": 4, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op4"},
            {"reqId": 5, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op5"},
        ]
        # Init ledgers
        leader_ledgers = []
        for name in ledger_names:
            ledger_of_leader, _ = await A.microledgers.create(name, genesis)
            leader_ledgers.append(ledger_of_leader)
            await B.microledgers.create(name, genesis)
            await C.microledgers.create(name, genesis)

        coro_committer = routine_of_txn_committer(
            A_params['server_address'], A_params['credentials'], A_params['p2p'],
            A2B.me, participants, leader_ledgers, txns
        )
        coro_acceptor1 = routine_of_txn_acceptor(
            B_params['server_address'], B_params['credentials'], B_params['p2p'],
        )
        coro_acceptor2 = routine_of_txn_acceptor(
            C_params['server_address'], C_params['credentials'], C_params['p2p'],
        )

        stamp1 = datetime.now()
        print('> begin')
        await run_coroutines(
            coro_committer,
            coro_acceptor1,
            coro_acceptor2,
            timeout=60
        )
        print('> end')
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        print(f'***** Consensus timeout: {delta.seconds}')

        for name in ledger_names:
            ledger_for_a = await A.microledgers.ledger(name)
            ledger_for_b = await B.microledgers.ledger(name)
            ledger_for_c = await C.microledgers.ledger(name)
            for ledger in [ledger_for_a, ledger_for_b, ledger_for_c]:
                all_txns = await ledger.get_all_transactions()
                assert 'op3' in str(all_txns)
                assert 'op4' in str(all_txns)
                assert 'op5' in str(all_txns)
    finally:
        await A.close()
        await B.close()
        await C.close()


@pytest.mark.asyncio
async def test_simple_consensus_error(A: Agent, B: Agent, C: Agent, ledger_name: str, test_suite: ServerTestSuite):
    A_params = test_suite.get_agent_params('agent1')
    B_params = test_suite.get_agent_params('agent2')
    C_params = test_suite.get_agent_params('agent3')
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
        ledger_for_a, _ = await A.microledgers.create(ledger_name, genesis)
        initial_state_root_hash = ledger_for_a.root_hash
        await B.microledgers.create(ledger_name, genesis)
        await C.microledgers.create(ledger_name, genesis)

        txns = [
            {"reqId": 3, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op3"},
            {"reqId": 4, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op4"},
            {"reqId": 5, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op5"},
        ]
        broken_txns = [
            {"reqId": 3, "identifier": "BROKEN-5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op3", "txnMetadata": {"seqNo": 4}},
            {"reqId": 4, "identifier": "BROKEN-2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op4", "txnMetadata": {"seqNo": 5}},
            {"reqId": 5, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op5", "txnMetadata": {"seqNo": 6}},
        ]
        broken_txns = [Transaction(txn) for txn in broken_txns]
        coro_committer = routine_of_txn_committer(
            A_params['server_address'], A_params['credentials'], A_params['p2p'],
            A2B.me, participants, ledger_for_a, txns
        )
        coro_acceptor1 = routine_of_txn_acceptor(
            B_params['server_address'], B_params['credentials'], B_params['p2p'], broken_txns
        )
        coro_acceptor2 = routine_of_txn_acceptor(
            C_params['server_address'], C_params['credentials'], C_params['p2p'], broken_txns
        )

        stamp1 = datetime.now()
        print('> begin')
        results = await run_coroutines(coro_committer, coro_acceptor1, coro_acceptor2, timeout=60)
        print('> end')
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        print(f'***** Consensus timeout: {delta.seconds}')
        for res in results:
            if type(res) is tuple:
                val = res[0]
            else:
                val = res
            assert val is False

        ledger_for_a = await A.microledgers.ledger(ledger_name)
        ledger_for_b = await B.microledgers.ledger(ledger_name)
        ledger_for_c = await C.microledgers.ledger(ledger_name)
        for ledger in [ledger_for_a, ledger_for_b, ledger_for_c]:
            await ledger.reload()
            assert ledger.root_hash == initial_state_root_hash
            all_txns = await ledger.get_all_transactions()
            assert 'op3' not in str(all_txns)
            assert 'op4' not in str(all_txns)
            assert 'op5' not in str(all_txns)
    finally:
        await A.close()
        await B.close()
        await C.close()
