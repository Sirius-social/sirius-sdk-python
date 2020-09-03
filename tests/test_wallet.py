import uuid
import json

import pytest

from sirius_sdk import Agent
from sirius_sdk.agent.wallet import RetrieveRecordOptions, CacheOptions, NYMRole


@pytest.mark.asyncio
async def test_crypto_pack_message(agent1: Agent, agent2: Agent):
    await agent1.open()
    await agent2.open()
    wallet_sender = agent1.wallet
    wallet_recipient = agent2.wallet
    try:
        verkey_sender = await wallet_sender.crypto.create_key()
        verkey_recipient = await wallet_recipient.crypto.create_key()
        assert verkey_recipient
        assert verkey_sender
        message = dict(content='Hello!')
        # 1: anon crypt mode
        wired_message1 = await wallet_sender.crypto.pack_message(message, [verkey_recipient])
        unpacked_message1 = await wallet_recipient.crypto.unpack_message(wired_message1)
        assert json.dumps(unpacked_message1['message'], sort_keys=True) == json.dumps(message, sort_keys=True)
        # 2: auth crypt mode
        wired_message2 = await wallet_sender.crypto.pack_message(message, [verkey_recipient], verkey_sender)
        unpacked_message2 = await wallet_recipient.crypto.unpack_message(wired_message2)
        assert json.dumps(unpacked_message2['message'], sort_keys=True) == json.dumps(message, sort_keys=True)
        assert wired_message2.decode() != wired_message1.decode()
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_crypto_sign(agent1: Agent, agent2: Agent):
    await agent1.open()
    await agent2.open()
    wallet_signer = agent1.wallet
    wallet_verifier = agent2.wallet
    try:
        key_signer = await wallet_signer.crypto.create_key()
        message = dict(content='Hello!')
        message_bytes = json.dumps(message).encode()
        signature = await wallet_signer.crypto.crypto_sign(key_signer, message_bytes)
        is_ok = await wallet_verifier.crypto.crypto_verify(key_signer, message_bytes, signature)
        assert is_ok is True

        key_signer2 = await wallet_signer.crypto.create_key()
        broken_signature = await wallet_signer.crypto.crypto_sign(key_signer, message_bytes)
        is_ok = await wallet_verifier.crypto.crypto_verify(key_signer2, message_bytes, broken_signature)
        assert is_ok is False
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_did_maintenance(agent1: Agent):
    await agent1.open()
    try:
        # 1: Create Key
        random_key = await agent1.wallet.did.create_key()
        assert random_key

        # 2: Set metadata
        metadata = dict(
            key1='value1',
            key2='value2'
        )
        await agent1.wallet.did.set_key_metadata(random_key, metadata)
        expected = json.dumps(metadata, sort_keys=True)
        metadata = await agent1.wallet.did.get_key_metadata(random_key)
        actual = json.dumps(metadata, sort_keys=True)
        assert expected == actual

        # 3: Create DID + Verkey
        did, verkey = await agent1.wallet.did.create_and_store_my_did()
        fully = await agent1.wallet.did.qualify_did(did, 'peer')
        assert did in fully

        # 4: Replace verkey
        verkey_new = await agent1.wallet.did.replace_keys_start(did=fully)
        assert verkey_new
        metadata_list = await agent1.wallet.did.list_my_dids_with_meta()
        assert any([m['tempVerkey'] == verkey_new for m in metadata_list])
        await agent1.wallet.did.replace_keys_apply(did=fully)
        metadata_list = await agent1.wallet.did.list_my_dids_with_meta()
        assert any([m['verkey'] == verkey_new for m in metadata_list])

        actual_verkey = await agent1.wallet.did.key_for_local_did(did=fully)
        assert verkey_new == actual_verkey
    finally:
        await agent1.close()


@pytest.mark.asyncio
async def test_their_did_maintenance(agent1: Agent, agent2: Agent):
    await agent1.open()
    await agent2.open()
    wallet_me = agent1.wallet
    wallet_their = agent2.wallet
    try:
        did_my, verkey_my = await wallet_me.did.create_and_store_my_did()
        did_their, verkey_their = await wallet_their.did.create_and_store_my_did()
        await wallet_me.did.store_their_did(did_their, verkey_their)
        metadata = dict(
            key1='value1',
            key2='value2'
        )
        await wallet_me.did.set_did_metadata(did_their, metadata)
        expected = json.dumps(metadata, sort_keys=True)
        metadata = await wallet_me.did.get_did_metadata(did_their)
        actual = json.dumps(metadata, sort_keys=True)
        assert expected == actual

        verkey = await wallet_me.did.key_for_local_did(did_their)
        assert verkey_their == verkey

        verkey_their_new = await wallet_their.did.replace_keys_start(did=did_their)
        await wallet_their.did.replace_keys_apply(did=did_their)
        await wallet_me.did.store_their_did(did_their, verkey_their_new)
        verkey = await wallet_me.did.key_for_local_did(did_their)
        assert verkey_their_new == verkey
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_record_value(agent1: Agent):
    await agent1.open()
    try:
        value = 'my-value-' + uuid.uuid4().hex
        my_id = 'my-id-' + uuid.uuid4().hex
        await agent1.wallet.non_secrets.add_wallet_record('type', my_id, value)
        opts = RetrieveRecordOptions()
        opts.check_all()
        value_info = await agent1.wallet.non_secrets.get_wallet_record('type', my_id, opts)
        assert value_info['id'] == my_id
        assert value_info['tags'] == {}
        assert value_info['value'] == value
        assert value_info['type'] == 'type'

        value_new = 'my-new-value-' + uuid.uuid4().hex
        await agent1.wallet.non_secrets.update_wallet_record_value('type', my_id, value_new)
        value_info = await agent1.wallet.non_secrets.get_wallet_record('type', my_id, opts)
        assert value_info['value'] == value_new

        await agent1.wallet.non_secrets.delete_wallet_record('type', my_id)
    finally:
        await agent1.close()


@pytest.mark.asyncio
async def test_record_value_with_tags(agent1: Agent):
    await agent1.open()
    try:
        value = 'my-value-' + uuid.uuid4().hex
        my_id = 'my-id-' + uuid.uuid4().hex
        tags = {
            'tag1': 'val1',
            '~tag2': 'val2'
        }
        await agent1.wallet.non_secrets.add_wallet_record('type', my_id, value, tags)
        opts = RetrieveRecordOptions()
        opts.check_all()
        value_info = await agent1.wallet.non_secrets.get_wallet_record('type', my_id, opts)
        assert value_info['id'] == my_id
        assert value_info['tags'] == tags
        assert value_info['value'] == value
        assert value_info['type'] == 'type'

        upd_tags = {
            'ext-tag': 'val3'
        }
        await agent1.wallet.non_secrets.update_wallet_record_tags('type', my_id, upd_tags)
        value_info = await agent1.wallet.non_secrets.get_wallet_record('type', my_id, opts)
        assert value_info['tags'] == upd_tags

        await agent1.wallet.non_secrets.add_wallet_record_tags('type', my_id, tags)
        value_info = await agent1.wallet.non_secrets.get_wallet_record('type', my_id, opts)
        assert value_info['tags'] == dict(**upd_tags, **tags)

        await agent1.wallet.non_secrets.delete_wallet_record_tags('type', my_id, ['ext-tag'])
        value_info = await agent1.wallet.non_secrets.get_wallet_record('type', my_id, opts)
        assert value_info['tags'] == tags
    finally:
        await agent1.close()


@pytest.mark.asyncio
async def test_record_value_with_tags_then_update(agent1: Agent):
    await agent1.open()
    try:
        value = 'my-value-' + uuid.uuid4().hex
        my_id = 'my-id-' + uuid.uuid4().hex
        await agent1.wallet.non_secrets.add_wallet_record('type', my_id, value)
        opts = RetrieveRecordOptions()
        opts.check_all()
        value_info = await agent1.wallet.non_secrets.get_wallet_record('type', my_id, opts)
        assert value_info['id'] == my_id
        assert value_info['tags'] == {}
        assert value_info['value'] == value
        assert value_info['type'] == 'type'

        tags1 = {
            'tag1': 'val1',
            '~tag2': 'val2'
        }

        await agent1.wallet.non_secrets.update_wallet_record_tags('type', my_id, tags1)
        value_info = await agent1.wallet.non_secrets.get_wallet_record('type', my_id, opts)
        assert value_info['tags'] == tags1

        tags2 = {
            'tag3': 'val3',
        }
        await agent1.wallet.non_secrets.update_wallet_record_tags('type', my_id, tags2)
        value_info = await agent1.wallet.non_secrets.get_wallet_record('type', my_id, opts)
        assert value_info['tags'] == tags2
    finally:
        await agent1.close()


@pytest.mark.asyncio
async def test_record_search(agent1: Agent):
    await agent1.open()
    try:
        id1 = 'id-1-' + uuid.uuid4().hex
        id2 = 'id-2-' + uuid.uuid4().hex
        value1 = 'value-1-' + uuid.uuid4().hex
        value2 = 'value-2-' + uuid.uuid4().hex
        marker_a = 'A-' + uuid.uuid4().hex
        marker_b = 'B-' + uuid.uuid4().hex
        opts = RetrieveRecordOptions()
        opts.check_all()
        tags1 = {
            'tag1': value1,
            '~tag2': '5',
            'marker': marker_a
        }
        tags2 = {
            'tag3': 'val3',
            '~tag4': value2,
            'marker': marker_b
        }
        await agent1.wallet.non_secrets.add_wallet_record('type', id1, 'value1', tags1)
        await agent1.wallet.non_secrets.add_wallet_record('type', id2, 'value2', tags2)

        query = {
            "tag1": value1
        }
        records, total = await agent1.wallet.non_secrets.wallet_search('type', query, opts)
        assert total == 1
        assert 'value-1' in str(records)

        query = {
            "$or": [{"tag1": value1}, {"~tag4": value2}]
        }
        records, total = await agent1.wallet.non_secrets.wallet_search('type', query, opts)
        assert len(records) == 1
        assert total == 2

        records, total = await agent1.wallet.non_secrets.wallet_search('type', query, opts, limit=1000)
        assert len(records) == 2
        assert total == 2

        query = {
            "marker": {"$in": [marker_a, marker_b]}
        }
        records, total = await agent1.wallet.non_secrets.wallet_search('type', query, opts)
        assert 2 == total
    finally:
        await agent1.close()


@pytest.mark.asyncio
async def test_register_schema_in_network(agent2: Agent, default_network: str):
    await agent2.open()
    try:
        seed = '000000000000000000000000Trustee1'
        did, verkey = await agent2.wallet.did.create_and_store_my_did(seed=seed)
        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, schema = await agent2.wallet.anoncreds.issuer_create_schema(
            did, schema_name, '1.0', ['attr1', 'attr2', 'attr3']
        )

        ok, response = await agent2.wallet.ledger.register_schema(default_network, did, schema.body)
        assert ok is True
    finally:
        await agent2.close()


@pytest.mark.asyncio
async def test_register_cred_def_in_network(agent2: Agent, default_network: str):
    await agent2.open()
    try:
        seed = '000000000000000000000000Trustee1'
        did, verkey = await agent2.wallet.did.create_and_store_my_did(seed=seed)
        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, schema = await agent2.wallet.anoncreds.issuer_create_schema(
            did, schema_name, '1.0', ['attr1', 'attr2', 'attr3']
        )

        ok, response = await agent2.wallet.ledger.register_schema(default_network, did, schema.body)
        assert ok is True

        opts = CacheOptions()
        schema_from_ledger = await agent2.wallet.cache.get_schema(default_network, did, schema_id, opts)

        cred_def_id, cred_def = await agent2.wallet.anoncreds.issuer_create_and_store_credential_def(
            did, schema_from_ledger, 'TAG'
        )
        ok, response = await agent2.wallet.ledger.register_cred_def(default_network, did, cred_def)
        assert ok is True
    finally:
        await agent2.close()


@pytest.mark.asyncio
async def test_nym_operations_in_network(agent1: Agent, agent2: Agent, default_network: str):
    await agent1.open()
    await agent2.open()
    steward = agent1.wallet
    actor = agent2.wallet
    try:
        seed = '000000000000000000000000Steward1'
        did_steward, verkey_steward = await steward.did.create_and_store_my_did(seed=seed)
        did_trustee, verkey_trustee = await actor.did.create_and_store_my_did()
        did_common, verkey_common = await actor.did.create_and_store_my_did()

        # Trust Anchor
        ok, response = await steward.ledger.write_nym(
            default_network, did_steward, did_trustee, verkey_trustee, 'Test-Trustee', NYMRole.TRUST_ANCHOR
        )
        assert ok is True
        ok, nym1 = await steward.ledger.read_nym(
            pool_name=default_network, submitter_did=did_steward, target_did=did_trustee
        )
        assert ok is True
        ok, nym2 = await steward.ledger.read_nym(
            pool_name=default_network, submitter_did=None, target_did=did_trustee
        )
        assert ok is True
        assert json.dumps(nym1, sort_keys=True) == json.dumps(nym2, sort_keys=True)
        assert nym1['role'] == str(NYMRole.TRUST_ANCHOR.value[0])

        # Common User
        ok, response = await steward.ledger.write_nym(
            default_network, did_steward, did_common, verkey_common, 'CommonUser', NYMRole.COMMON_USER
        )
        assert ok is True
        ok, nym3 = await steward.ledger.read_nym(
            pool_name=default_network, submitter_did=None, target_did=did_common
        )
        assert ok is True
        assert nym3['role'] is None

        # Reset
        ok, response = await actor.ledger.write_nym(
            default_network, did_common, did_common, verkey_common, 'ResetUser', NYMRole.RESET
        )
        assert ok is True
        ok, nym4 = await steward.ledger.read_nym(
            pool_name=default_network, submitter_did=None, target_did=did_common
        )
        assert ok is True
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_attribute_operations_in_network(agent1: Agent, agent2: Agent, default_network: str):
    await agent1.open()
    await agent2.open()
    steward = agent1.wallet
    actor = agent2.wallet
    try:
        seed = '000000000000000000000000Steward1'
        did_steward, verkey_steward = await steward.did.create_and_store_my_did(seed=seed)
        did_common, verkey_common = await actor.did.create_and_store_my_did()
        ok, response = await steward.ledger.write_nym(
            default_network, did_steward, did_common, verkey_common, 'CommonUser', NYMRole.COMMON_USER
        )
        assert ok is True

        ok, response = await actor.ledger.write_attribute(
            default_network, did_common, did_common, 'attribute', 'value'
        )
        assert ok is True

        ok, response = await steward.ledger.read_attribute(
            default_network, did_steward, did_common, 'attribute'
        )
        assert ok is True
        assert response == 'value'
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_issue_verify_credential_in_network(agent1: Agent, agent2: Agent, agent3: Agent, default_network: str):
    await agent1.open()
    await agent2.open()
    await agent3.open()
    issuer = agent1.wallet
    holder = agent2.wallet
    verifier = agent3.wallet
    try:
        assert 1
    finally:
        await agent1.close()
        await agent2.close()
        await agent3.close()
