import uuid

import pytest

import sirius_sdk
from sirius_sdk.agent.wallet.abstract.non_secrets import RetrieveRecordOptions
from .helpers import ServerTestSuite


@pytest.mark.asyncio
async def test_record_value_ops(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent4')
    async with sirius_sdk.context(params['server_address'], params['credentials'], params['p2p']):
        value = 'my-value'
        my_id = 'my-id-' + uuid.uuid4().hex
        await sirius_sdk.NonSecrets.add_wallet_record('type', my_id, value)
        opts = RetrieveRecordOptions()
        opts.check_all()
        value_info = await sirius_sdk.NonSecrets.get_wallet_record('type', my_id, opts)
        assert value_info['id'] == my_id
        assert value_info['tags'] == {}
        assert value_info['value'] == value
        assert value_info['type'] == 'type'

        value_new = 'my-new-value'
        await sirius_sdk.NonSecrets.update_wallet_record_value('type', my_id, value_new)
        value_info = await sirius_sdk.NonSecrets.get_wallet_record('type', my_id, opts)
        assert value_info['value'] == value_new
        await sirius_sdk.NonSecrets.delete_wallet_record('type', my_id)


@pytest.mark.asyncio
async def test_record_tags_ops(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent4')
    async with sirius_sdk.context(params['server_address'], params['credentials'], params['p2p']):
        my_id = 'my-id-' + uuid.uuid4().hex

        value = 'my-value'
        tags = {
            'tag1': 'val1',
            '~tag2': 'val2'
        }
        await sirius_sdk.NonSecrets.add_wallet_record('type', my_id, value, tags)
        opts = RetrieveRecordOptions()
        opts.check_all()
        value_info = await sirius_sdk.NonSecrets.get_wallet_record('type', my_id, opts)
        assert value_info['id'] == my_id
        assert value_info['tags'] == tags
        assert value_info['value'] == value
        assert value_info['type'] == 'type'

        upd_tags = {
            'ext-tag': 'val3'
        }
        await sirius_sdk.NonSecrets.update_wallet_record_tags('type', my_id, upd_tags)
        value_info = await sirius_sdk.NonSecrets.get_wallet_record('type', my_id, opts)
        assert value_info['tags'] == upd_tags

        await sirius_sdk.NonSecrets.add_wallet_record_tags('type', my_id, tags)
        value_info = await sirius_sdk.NonSecrets.get_wallet_record('type', my_id, opts)
        assert value_info['tags'] == dict(**upd_tags, **tags)

        await sirius_sdk.NonSecrets.delete_wallet_record_tags('type', my_id, ['ext-tag'])
        value_info = await sirius_sdk.NonSecrets.get_wallet_record('type', my_id, opts)
        assert value_info['tags'] == tags


@pytest.mark.asyncio
async def test_maintain_tags_only_update_ops(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent4')
    async with sirius_sdk.context(params['server_address'], params['credentials'], params['p2p']):
        my_id = 'my-id-' + uuid.uuid4().hex
        value = 'my-value'
        await sirius_sdk.NonSecrets.add_wallet_record('type', my_id, value, )
        opts = RetrieveRecordOptions()
        opts.check_all()
        value_info = await sirius_sdk.NonSecrets.get_wallet_record('type', my_id, opts)
        assert value_info['id'] == my_id
        assert value_info['tags'] == {}
        assert value_info['value'] == value
        assert value_info['type'] == 'type'

        tags1 = {
            'tag1': 'val1',
            '~tag2': 'val2'
        }

        await sirius_sdk.NonSecrets.update_wallet_record_tags('type', my_id, tags1)
        value_info = await sirius_sdk.NonSecrets.get_wallet_record('type', my_id, opts)
        assert value_info['tags'] == tags1

        tags2 = {
            'tag3': 'val3',
        }
        await sirius_sdk.NonSecrets.update_wallet_record_tags('type', my_id, tags2)
        value_info = await sirius_sdk.NonSecrets.get_wallet_record('type', my_id, opts)
        assert value_info['tags'] == tags2


@pytest.mark.asyncio
async def test_wallet_search_sqlite(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent4')
    async with sirius_sdk.context(params['server_address'], params['credentials'], params['p2p']):
        my_id1 = 'my-id-' + uuid.uuid4().hex
        my_id2 = 'my-id-' + uuid.uuid4().hex
        type_ = 'type_' + uuid.uuid4().hex
        opts = RetrieveRecordOptions()
        opts.check_all()
        tags1 = {
            'tag1': 'val1',
            '~tag2': '5',
            'marker': 'A'
        }
        tags2 = {
            'tag3': 'val3',
            '~tag4': '6',
            'marker': 'B'
        }
        await sirius_sdk.NonSecrets.add_wallet_record(type_, my_id1, 'value1', tags1)
        await sirius_sdk.NonSecrets.add_wallet_record(type_, my_id2, 'value2', tags2)

        query = {
            "tag1": "val1"
        }
        records, total = await sirius_sdk.NonSecrets.wallet_search(type_, query, opts)
        assert total == 1
        assert 'value1' in str(records)

        query = {
            "$or": [{"tag1": "val1"}, {"~tag4": "6"}]
        }
        records, total = await sirius_sdk.NonSecrets.wallet_search(type_, query, opts)
        assert len(records) == 1
        assert total == 2

        records, total = await sirius_sdk.NonSecrets.wallet_search(type_, query, opts, limit=1000)
        assert len(records) == 2
        assert total == 2

        query = {
            "marker": {"$in": ["A", "C"]}
        }
        records, total = await sirius_sdk.NonSecrets.wallet_search(type_, query, opts)
        assert 1 == total
