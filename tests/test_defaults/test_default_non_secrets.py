import uuid

import pytest

import sirius_sdk

from sirius_sdk.hub.defaults.default_non_secrets import DefaultNonSecretsStorage
from sirius_sdk.agent.wallet.abstract.non_secrets import RetrieveRecordOptions
from sirius_sdk.hub.defaults.default_storage import InMemoryKeyValueStorage


@pytest.mark.asyncio
async def test_record_value_ops():
    obj_under_test = DefaultNonSecretsStorage(storage=InMemoryKeyValueStorage())
    type_under_test = 'type_' + uuid.uuid4().hex
    value = 'my-value'
    my_id = 'my-id-' + uuid.uuid4().hex
    await obj_under_test.add_wallet_record(type_under_test, my_id, value)
    opts = RetrieveRecordOptions()
    opts.check_all()
    value_info = await obj_under_test.get_wallet_record(type_under_test, my_id, opts)
    assert value_info['id'] == my_id
    assert value_info['tags'] == {}
    assert value_info['value'] == value
    assert value_info['type'] == type_under_test

    value_new = 'my-new-value'
    await obj_under_test.update_wallet_record_value(type_under_test, my_id, value_new)
    value_info = await obj_under_test.get_wallet_record(type_under_test, my_id, opts)
    assert value_info['value'] == value_new
    await obj_under_test.delete_wallet_record(type_under_test, my_id)


@pytest.mark.asyncio
async def test_record_tags_ops():
    obj_under_test = DefaultNonSecretsStorage(storage=InMemoryKeyValueStorage())
    type_under_test = 'type_' + uuid.uuid4().hex

    my_id = 'my-id-' + uuid.uuid4().hex

    value = 'my-value'
    tags = {
        'tag1': 'val1',
        '~tag2': 'val2'
    }
    await obj_under_test.add_wallet_record(type_under_test, my_id, value, tags)
    opts = RetrieveRecordOptions()
    opts.check_all()
    value_info = await obj_under_test.get_wallet_record(type_under_test, my_id, opts)
    assert value_info['id'] == my_id
    assert value_info['tags'] == tags
    assert value_info['value'] == value
    assert value_info['type'] == type_under_test

    upd_tags = {
        'ext-tag': 'val3'
    }
    await obj_under_test.update_wallet_record_tags(type_under_test, my_id, upd_tags)
    value_info = await obj_under_test.get_wallet_record(type_under_test, my_id, opts)
    assert value_info['tags'] == upd_tags

    await obj_under_test.add_wallet_record_tags(type_under_test, my_id, tags)
    value_info = await obj_under_test.get_wallet_record(type_under_test, my_id, opts)
    assert value_info['tags'] == dict(**upd_tags, **tags)

    await obj_under_test.delete_wallet_record_tags(type_under_test, my_id, ['ext-tag'])
    value_info = await obj_under_test.get_wallet_record(type_under_test, my_id, opts)
    assert value_info['tags'] == tags


@pytest.mark.asyncio
async def test_maintain_tags_only_update_ops():
    obj_under_test = DefaultNonSecretsStorage(storage=InMemoryKeyValueStorage())
    type_under_test = 'type_' + uuid.uuid4().hex

    my_id = 'my-id-' + uuid.uuid4().hex
    value = 'my-value'
    await obj_under_test.add_wallet_record(type_under_test, my_id, value, )
    opts = RetrieveRecordOptions()
    opts.check_all()
    value_info = await obj_under_test.get_wallet_record(type_under_test, my_id, opts)
    assert value_info['id'] == my_id
    assert value_info['tags'] == {}
    assert value_info['value'] == value
    assert value_info['type'] == type_under_test

    tags1 = {
        'tag1': 'val1',
        '~tag2': 'val2'
    }

    await obj_under_test.update_wallet_record_tags(type_under_test, my_id, tags1)
    value_info = await obj_under_test.get_wallet_record(type_under_test, my_id, opts)
    assert value_info['tags'] == tags1

    tags2 = {
        'tag3': 'val3',
    }
    await obj_under_test.update_wallet_record_tags(type_under_test, my_id, tags2)
    value_info = await obj_under_test.get_wallet_record(type_under_test, my_id, opts)
    assert value_info['tags'] == tags2


@pytest.mark.asyncio
async def test_wallet_search():
    obj_under_test = DefaultNonSecretsStorage(storage=InMemoryKeyValueStorage())

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
    await obj_under_test.add_wallet_record(type_, my_id1, 'value1', tags1)
    await obj_under_test.add_wallet_record(type_, my_id2, 'value2', tags2)

    query = {
        "tag1": "val1"
    }
    records, total = await obj_under_test.wallet_search(type_, query, opts)
    assert total == 1
    assert 'value1' in str(records)

    query = {
        "tag1": "val1",
        "marker": "A"
    }
    records, total = await obj_under_test.wallet_search(type_, query, opts)
    assert total == 1
    assert 'value1' in str(records)

    query = {
        "$or": [{"tag1": "val1"}, {"~tag4": "6"}]
    }
    records, total = await obj_under_test.wallet_search(type_, query, opts)
    assert len(records) == 1
    assert total == 2

    records, total = await obj_under_test.wallet_search(type_, query, opts, limit=1000)
    assert len(records) == 2
    assert total == 2

    query = {
        "marker": {"$in": ["A", "C"]}
    }
    records, total = await obj_under_test.wallet_search(type_, query, opts)
    assert 1 == total
