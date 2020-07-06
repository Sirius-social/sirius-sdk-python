import uuid

import pytest

from sirius_sdk import Agent
from sirius_sdk.agent.ledger import SchemaFilters, CredentialDefinition


@pytest.mark.asyncio
async def test_schema_registration(agent1: Agent):
    await agent1.open()
    try:
        seed = '000000000000000000000000Steward1'
        did, verkey = await agent1.wallet.did.create_and_store_my_did(seed=seed)
        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, anoncred_schema = await agent1.wallet.anoncreds.issuer_create_schema(
            did, schema_name, '1.0', ['attr1', 'attr2', 'attr3']
        )
        ledger = agent1.ledger('default')

        ok, schema = await ledger.register_schema(schema=anoncred_schema, submitter_did=did)
        assert ok is True
        assert schema.seq_no > 0

        ok, _ = await ledger.register_schema(schema=anoncred_schema, submitter_did=did)
        assert ok is False

        restored_schema = await ledger.ensure_schema_exists(schema=anoncred_schema, submitter_did=did)
        assert restored_schema is not None
        assert restored_schema == schema

    finally:
        await agent1.close()


@pytest.mark.asyncio
async def test_schema_loading(agent1: Agent, agent2: Agent):
    await agent1.open()
    await agent2.open()
    try:
        seed1 = '000000000000000000000000Steward1'
        did1, verkey1 = await agent1.wallet.did.create_and_store_my_did(seed=seed1)
        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, anoncred_schema = await agent1.wallet.anoncreds.issuer_create_schema(
            did1, schema_name, '1.0', ['attr1', 'attr2', 'attr3']
        )
        ledger1 = agent1.ledger('default')

        ok, schema = await ledger1.register_schema(schema=anoncred_schema, submitter_did=did1)
        assert ok is True
        assert schema.seq_no > 0

        seed2 = '000000000000000000000000Trustee0'
        did2, verkey2 = await agent2.wallet.did.create_and_store_my_did(seed=seed2)
        ledger2 = agent2.ledger('default')
        loaded_schema = await ledger2.load_schema(id_=schema.id, submitter_did=did2)
        assert loaded_schema is not None
        assert loaded_schema == schema
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_schema_fetching(agent1: Agent):
    await agent1.open()
    try:
        seed = '000000000000000000000000Steward1'
        did, verkey = await agent1.wallet.did.create_and_store_my_did(seed=seed)
        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, anoncred_schema = await agent1.wallet.anoncreds.issuer_create_schema(
            did, schema_name, '1.0', ['attr1', 'attr2', 'attr3']
        )
        ledger = agent1.ledger('default')

        ok, schema = await ledger.register_schema(schema=anoncred_schema, submitter_did=did)
        assert ok is True

        filters = SchemaFilters()
        filters.name = schema_name

        fetches = await ledger.fetch_schemas(filters)
        assert len(fetches) == 1
        assert fetches[0].issuer_did == did

    finally:
        await agent1.close()


@pytest.mark.asyncio
async def test_register_cred_def(agent1: Agent):
    await agent1.open()
    try:
        seed = '000000000000000000000000Steward1'
        did, verkey = await agent1.wallet.did.create_and_store_my_did(seed=seed)
        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, anoncred_schema = await agent1.wallet.anoncreds.issuer_create_schema(
            did, schema_name, '1.0', ['attr1', 'attr2', 'attr3']
        )
        ledger = agent1.ledger('default')

        ok, schema = await ledger.register_schema(schema=anoncred_schema, submitter_did=did)
        assert ok is True

        cred_def = CredentialDefinition(tag='Test Tag', schema=schema)
        assert cred_def.body is None
        ok, ledger_cred_def = await ledger.register_cred_def(cred_def=cred_def, submitter_did=did)
        assert ok is True
        assert ledger_cred_def.body is not None
        assert ledger_cred_def.seq_no > 0

        ok, ledger_cred_def2 = await ledger.register_cred_def(cred_def=cred_def, submitter_did=did)
        assert ok is True
        assert ledger_cred_def.body == ledger_cred_def2.body
        assert ledger_cred_def2.seq_no > ledger_cred_def.seq_no

    finally:
        await agent1.close()
