import pytest

from sirius_sdk.storages import InMemoryKeyValueStorage, InMemoryImmutableCollection


@pytest.mark.asyncio
async def test_inmemory_kv_storage():
    kv = InMemoryKeyValueStorage()
    await kv.select_db('db1')

    await kv.set('key1', 'value1')
    value = await kv.get('key1')
    assert value == 'value1'

    await kv.select_db('db2')
    await kv.set('key1', 1000)
    value = await kv.get('key1')
    assert value == 1000

    await kv.select_db('db1')
    value = await kv.get('key1')
    assert value == 'value1'

    await kv.delete('key1')
    value = await kv.get('key1')
    assert value is None

    await kv.delete('unknown-key')


@pytest.mark.asyncio
async def test_inmemory_immutable_collection():
    collection = InMemoryImmutableCollection()

    await collection.select_db('db1')
    await collection.add('Value1', {'tag1': 'tag-val-1', 'tag2': 'tag-val-2'})
    await collection.add('Value2', {'tag1': 'tag-val-1', 'tag2': 'tag-val-3'})

    fetched1 = await collection.fetch({'tag1': 'tag-val-1'})
    assert len(fetched1) == 2

    fetched1 = await collection.fetch({'tag2': 'tag-val-2'})
    assert len(fetched1) == 1
    assert fetched1[0] == 'Value1'

    await collection.select_db('db2')
    fetched3 = await collection.fetch({})
    assert len(fetched3) == 0