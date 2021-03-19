import uuid
from datetime import datetime

import pytest

from sirius_sdk import Agent
from sirius_sdk.errors.exceptions import SiriusPromiseContextException
from sirius_sdk.agent.microledgers.abstract import Transaction, LedgerMeta, AbstractMicroledger


def get_state(ledger: AbstractMicroledger) -> dict:
    return {
        'name': ledger.name,
        'seq_no': ledger.seq_no,
        'size': ledger.size,
        'uncommitted_size': ledger.uncommitted_size,
        'root_hash': ledger.root_hash,
        'uncommitted_root_hash': ledger.uncommitted_root_hash
    }


@pytest.mark.asyncio
async def test_init_ledger(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"},
            {"reqId": 2, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op2"},
            {"reqId": 3, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op3"}
        ]
        ledger, txns = await agent4.microledgers.create(ledger_name, genesis_txns)
        assert ledger.root_hash == '3u8ZCezSXJq72H5CdEryyTuwAKzeZnCZyfftJVFr7y8U'
        assert all([isinstance(txn, Transaction) for txn in txns])
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_merkle_info(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"},
            {"reqId": 2, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op2"},
            {"reqId": 3, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op3"},
            {"reqId": 4, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op4"},
            {"reqId": 5, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op5"},
        ]
        ledger, txns = await agent4.microledgers.create(ledger_name, genesis_txns)
        merkle_info = await ledger.merkle_info(4)
        assert merkle_info.root_hash == 'CwX1TRYKpejHmdnx3gMgHtSioDzhDGTASAD145kjyyRh'
        assert merkle_info.audit_path == ['46kxvYf7RjRERXdS56vUpFCzm2A3qRYSLaRr6tVT6tSd', '3sgNJmsXpmin7P5C6jpHiqYfeWwej5L6uYdYoXTMc1XQ']
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_append_operations(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"}
        ]
        ledger, _ = await agent4.microledgers.create(ledger_name, genesis_txns)
        txns = [
            {"reqId": 2, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op2"},
            {"reqId": 3, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op3"},
        ]
        txn_time = str(datetime.now())
        start, end, appended_transactions = await ledger.append(txns, txn_time)
        assert end == 3
        assert start == 2
        assert all([isinstance(txn, Transaction) for txn in appended_transactions])
        assert txn_time in str(appended_transactions)
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_commit_discard(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"}
        ]
        ledger, _ = await agent4.microledgers.create(ledger_name, genesis_txns)
        txns = [
            {"reqId": 2, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op2"},
            {"reqId": 3, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op3"},
        ]
        txn_time = str(datetime.now())

        assert ledger.uncommitted_root_hash == ledger.root_hash
        await ledger.append(txns, txn_time)
        assert ledger.uncommitted_root_hash != ledger.root_hash
        assert ledger.size == 1
        assert ledger.uncommitted_size == 3

        # COMMIT
        await ledger.commit(1)
        assert ledger.size == 2
        assert ledger.uncommitted_size == 3
        assert ledger.uncommitted_root_hash != ledger.root_hash

        # DISCARD
        await ledger.discard(1)
        assert ledger.size == 2
        assert ledger.uncommitted_size == 2
        assert ledger.uncommitted_root_hash == ledger.root_hash

    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_reset_uncommitted(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"}
        ]
        ledger, _ = await agent4.microledgers.create(ledger_name, genesis_txns)
        txns = [
            {"reqId": 2, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op2"},
            {"reqId": 3, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op3"},
        ]
        await ledger.append(txns)
        uncommitted_size_before = ledger.uncommitted_size
        await ledger.reset_uncommitted()
        uncommitted_size_after = ledger.uncommitted_size

        assert uncommitted_size_after != uncommitted_size_before
        assert uncommitted_size_after == 1
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_get_operations(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"},
            {"reqId": 2, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op2"},
            {"reqId": 3, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op3"}
        ]
        ledger, _ = await agent4.microledgers.create(ledger_name, genesis_txns)
        txns = [
            {"reqId": 4, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op4"},
            {"reqId": 5, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op5"},
        ]
        await ledger.append(txns)

        # 1 get_last_committed_txn
        txn = await ledger.get_last_committed_transaction()
        assert isinstance(txn, Transaction)
        assert 'op3' in str(txn)

        # 2 get_last_txn
        txn = await ledger.get_last_transaction()
        assert isinstance(txn, Transaction)
        assert 'op5' in str(txn)

        # 3 get_uncommitted_txns
        txns = await ledger.get_uncommitted_transactions()
        assert all([isinstance(txn, Transaction) for txn in txns])
        assert all(op in str(txns) for op in ['op4', 'op5']) is True
        assert any(op in str(txns) for op in ['op1', 'op2', 'op3']) is False

        # 4 get_by_seq_no
        txn = await ledger.get_transaction(seq_no=1)
        assert isinstance(txn, Transaction)
        assert 'op1' in str(txn)

        # 5 get_by_seq_no_uncommitted
        txn = await ledger.get_uncommitted_transaction(seq_no=4)
        assert isinstance(txn, Transaction)
        assert 'op4' in str(txn)
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_reset(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"},
            {"reqId": 2, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op2"},
            {"reqId": 3, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op3"},
            {"reqId": 4, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op4"},
            {"reqId": 5, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op5"},
        ]
        ledger, _ = await agent4.microledgers.create(ledger_name, genesis_txns)
        assert ledger.size == 5

        is_exists = await agent4.microledgers.is_exists(ledger_name)
        assert is_exists is True

        await agent4.microledgers.reset(ledger_name)
        is_exists = await agent4.microledgers.is_exists(ledger_name)
        assert is_exists is False
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_list(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"},
            {"reqId": 2, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op2"},
            {"reqId": 3, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op3"}
        ]
        ledger, _ = await agent4.microledgers.create(ledger_name, genesis_txns)
        # Get List
        collection = await agent4.microledgers.list()
        assert ledger_name in str(collection)
        assert all([isinstance(meta, LedgerMeta) for meta in collection])

        # Is exists
        ok = await agent4.microledgers.is_exists(ledger_name)
        assert ok is True

        # Reset Calling
        await agent4.microledgers.reset(ledger_name)

        # Get List
        collection = await agent4.microledgers.list()
        assert ledger_name not in str(collection)
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_get_all_txns(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"},
            {"reqId": 2, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op2"},
            {"reqId": 3, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op3"}
        ]
        ledger, _ = await agent4.microledgers.create(ledger_name, genesis_txns)
        txns = [
            {"reqId": 4, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op4"},
            {"reqId": 5, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op5"},
        ]
        await ledger.append(txns)

        txns = await ledger.get_all_transactions()
        assert all([isinstance(txn, Transaction) for txn in txns])
        assert all(op in str(txns) for op in ['op4', 'op5']) is False
        assert any(op in str(txns) for op in ['op1', 'op2', 'op3']) is True
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_audit_proof(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"},
            {"reqId": 2, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op2"},
            {"reqId": 3, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op3"},
            {"reqId": 4, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op4"},
            {"reqId": 5, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op5"},
            {"reqId": 6, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op6"},
        ]
        ledger, _ = await agent4.microledgers.create(ledger_name, genesis_txns)
        txns = [
            {"reqId": 7, "identifier": "2btLJAAb1S3x6hZYdVyAePjqtQYi2ZBSRGy4569RZu8h", "op": "op7"},
            {"reqId": 8, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op8"},
            {"reqId": 9, "identifier": "CECeGXDi6EHuhpwz19uyjjEnsRGNXodFYqCRgdLmLRkt", "op": "op9"},
        ]
        await ledger.append(txns)

        audit_paths = []
        for seq_no in [1, 2, 3, 4, 5, 6]:
            audit_proof = await ledger.audit_proof(seq_no)
            assert audit_proof.root_hash == '3eDS4j8HgpAyRnuvfFG624KKvQBuNXKBenhqHmHtUgeq'
            assert audit_proof.ledger_size == 6
            assert audit_proof.audit_path not in audit_paths
            audit_paths.append(audit_proof.audit_path)

        for seq_no in [7, 8, 9]:
            audit_proof = await ledger.audit_proof(seq_no)
            assert audit_proof.root_hash == '3eDS4j8HgpAyRnuvfFG624KKvQBuNXKBenhqHmHtUgeq'
            assert audit_proof.ledger_size == 6
            audit_paths.append(audit_proof.audit_path)
            assert ledger.uncommitted_root_hash == 'Dkoca8Af15uMLBHAqbddwqmpiqsaDEtKDoFVfNRXt44g'
        print('@')
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_leaf_hash(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"}
        ]
        ledger, txns = await agent4.microledgers.create(ledger_name, genesis_txns)
        txn = txns[0]
        leaf_hash = await agent4.microledgers.leaf_hash(txn)
        assert isinstance(leaf_hash, bytes)
        expected = b'y\xd9\x92\x9f\xd1\xe7\xf1o\t\x9c&\xb6\xf4HP\xda\x04J\xd0\xfeQ\xe9.X-\x9c\xa3r\xf2\xb8\xb90'
        assert expected == leaf_hash
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_rename(agent4: Agent, ledger_name: str):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1"}
        ]
        ledger, _ = await agent4.microledgers.create(ledger_name, genesis_txns)

        new_name = 'new_name_' + uuid.uuid4().hex
        await ledger.rename(new_name)
        assert ledger.name == new_name

        is_exists1 = await agent4.microledgers.is_exists(ledger_name)
        is_exists2 = await agent4.microledgers.is_exists(new_name)
        assert is_exists1 is False
        assert is_exists2 is True
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_batched_ops(agent4: Agent, ledger_names: list):
    await agent4.open()
    try:
        genesis_txns = [
            {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1", 'txnMetadata': {}}
        ]
        reset_txns = [
            {"reqId": 2, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op2", 'txnMetadata': {}}
        ]
        commit_txns = [
            {"reqId": 3, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op3", 'txnMetadata': {}}
        ]
        txn_time = str(datetime.utcnow())

        for ledger_name in ledger_names:
            await agent4.microledgers.create(ledger_name, genesis_txns)

        batched = await agent4.microledgers.batched()
        ledgers = await batched.open(ledger_names)
        try:
            assert all(ledger.name in ledger_names for ledger in ledgers)
            # Fetch states
            ledgers = await batched.states()
            states_before = {ledger.name: get_state(ledger) for ledger in ledgers}
            assert set(states_before.keys()) == set(ledger_names)
            # Append
            ledgers = await batched.append(reset_txns)
            states_after_append = {ledger.name: get_state(ledger) for ledger in ledgers}
            assert set(states_after_append.keys()) == set(ledger_names)
            for ledger_name_, state_ in states_after_append.items():
                assert state_['uncommitted_size'] == 2
            # Reset uncommitted
            ledgers = await batched.reset_uncommitted()
            states_after_reset_uncommitted = {ledger.name: get_state(ledger) for ledger in ledgers}
            assert set(states_after_reset_uncommitted.keys()) == set(ledger_names)
            for ledger_name_, state_ in states_after_reset_uncommitted.items():
                assert state_['uncommitted_size'] == 1
            # Append + Commit
            await batched.append(commit_txns, txn_time=txn_time)
            ledgers = await batched.commit()
            states_after_commit = {ledger.name: get_state(ledger) for ledger in ledgers}
            for ledger_name_, state_ in states_after_commit.items():
                assert state_['uncommitted_size'] == 2
                assert state_['size'] == 2
            # Check all txns
            for ledger_name in ledger_names:
                ledger = await agent4.microledgers.ledger(ledger_name)
                txns = await ledger.get_all_transactions()
                assert 'op1' in str(txns)
                assert 'op2' not in str(txns)
                assert 'op3' in str(txns)
                assert txn_time in str(txns)
        finally:
            await batched.close()
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_batched_ops_performance(agent4: Agent):
    genesis_txns = [
        {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1", 'txnMetadata': {}}
    ]
    commit_txns = [
        {"reqId": 2, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op3", 'txnMetadata': {}}
    ]
    await agent4.open()
    try:
        # Calc timeout for ledgers count = 2
        ledger_names = [f'Ledger-{uuid.uuid4().hex}' for n in range(2)]
        for ledger_name in ledger_names:
            await agent4.microledgers.create(ledger_name, genesis_txns)
        batched = await agent4.microledgers.batched()
        await batched.open(ledger_names)
        try:
            stamp1 = datetime.now()
            await batched.append(commit_txns)
            ledgers = await batched.commit()
            stamp2 = datetime.now()
        finally:
            await batched.close()
        delta = stamp2 - stamp1
        seconds_for_2 = delta.total_seconds()
        print('========== Timeout for 2 Ledgers =======')
        print(f'\tSeconds: {seconds_for_2}')
        print('========================================')
        # Calc timeout for ledgers count = 100
        ledger_names = [f'Ledger-{uuid.uuid4().hex}' for n in range(100)]
        for ledger_name in ledger_names:
            await agent4.microledgers.create(ledger_name, genesis_txns)
        batched = await agent4.microledgers.batched()
        await batched.open(ledger_names)
        try:
            stamp1 = datetime.now()
            await batched.append(commit_txns)
            await batched.commit()
            stamp2 = datetime.now()
        finally:
            await batched.close()
        delta = stamp2 - stamp1
        seconds_for_100 = delta.total_seconds()
        print('========== Timeout for 100 Ledgers =======')
        print(f'\tSeconds: {seconds_for_100}')
        print('========================================')
        assert seconds_for_100 < 50 * seconds_for_2
        # Check for 100 ledgers out-of batched mode
        ledger_names = [f'Ledger-{uuid.uuid4().hex}' for n in range(100)]
        ledgers = []
        for ledger_name in ledger_names:
            ledger, txns = await agent4.microledgers.create(ledger_name, genesis_txns)
            ledgers.append(ledger)
        stamp1 = datetime.now()
        for ledger in ledgers:
            await ledger.append(commit_txns)
            await ledger.commit(count=len(commit_txns))
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        seconds_for_100_non_parallel = delta.total_seconds()
        print('========== Timeout for 100 Ledgers Non-parallel mode=======')
        print(f'\tSeconds: {seconds_for_100_non_parallel}')
        print('========================================')
        assert seconds_for_100 < seconds_for_100_non_parallel/2
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_microledgers_in_same_context_space_1(agent4: Agent, ledger_name: str):
    genesis_txns = [
        {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1", 'txnMetadata': {}}
    ]
    commit_txns = [
        {"reqId": 2, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op3", 'txnMetadata': {}}
    ]
    await agent4.open()
    try:
        await agent4.microledgers.create(ledger_name, genesis_txns)
        batched = await agent4.microledgers.batched()
        await batched.open([ledger_name])
        try:
            ledgers = await batched.append(commit_txns)
            ledger_from_batched = ledgers[0]

            ledger_from_local = await agent4.microledgers.ledger(ledger_name)

            assert 2 == ledger_from_batched.uncommitted_size == ledger_from_local.uncommitted_size

            await batched.append(commit_txns)
            assert ledger_from_local.uncommitted_size == 3

        finally:
            await batched.close()
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_microledgers_in_same_context_space_2(agent4: Agent, ledger_name: str):
    genesis_txns = [
        {"reqId": 1, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op1", 'txnMetadata': {}}
    ]
    commit_txns = [
        {"reqId": 2, "identifier": "5rArie7XKukPCaEwq5XGQJnM9Fc5aZE3M9HAPVfMU2xC", "op": "op3", 'txnMetadata': {}}
    ]
    await agent4.open()
    try:
        await agent4.microledgers.create(ledger_name, genesis_txns)
    finally:
        await agent4.close()

    # Next open iteration refresh Agent context
    await agent4.open()
    try:
        batched = await agent4.microledgers.batched()
        await batched.open([ledger_name])
        try:
            ledgers = await batched.append(commit_txns)
            ledger_from_batched = ledgers[0]

            ledger_from_local = await agent4.microledgers.ledger(ledger_name)

            assert 2 == ledger_from_batched.uncommitted_size == ledger_from_local.uncommitted_size

            await batched.append(commit_txns)
            assert ledger_from_local.uncommitted_size == 3

        finally:
            await batched.close()
    finally:
        await agent4.close()


@pytest.mark.asyncio
async def test_batched_ops_errors(agent4: Agent, ledger_names: list):
    await agent4.open()
    try:
        api = await agent4.microledgers.batched()
        try:
            await api.open(['missing-ledger-name'])
        except SiriusPromiseContextException as e:
            exc = e
        else:
            exc = None
        assert exc is not None
    finally:
        await agent4.close()
