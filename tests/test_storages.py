import uuid

import pytest

from sirius_sdk import Agent
from sirius_sdk.agent.storages import InWalletImmutableCollection
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


@pytest.mark.asyncio
async def test_inwallet_immutable_collection(agent1: Agent):
    await agent1.open()
    try:
        collection = InWalletImmutableCollection(agent1.wallet.non_secrets)

        value1 = {
            'key1': 'value1',
            'key2': 10000
        }
        value2 = {
            'key1': 'value2',
            'key2': 50000
        }

        await collection.select_db(db_name=uuid.uuid4().hex)
        await collection.add(value1, {'tag': 'value1'})
        await collection.add(value2, {'tag': 'value2'})

        fetched, count = await collection.fetch({'tag': 'value1'})
        assert count == 1
        assert len(fetched) == 1
        assert fetched[0] == value1

        fetched, count = await collection.fetch({'tag': 'value2'})
        assert count == 1
        assert len(fetched) == 1
        assert fetched[0] == value2

        fetched, count = await collection.fetch({})
        assert count == 2

        await collection.select_db(db_name=uuid.uuid4().hex)
        fetched, count = await collection.fetch({})
        assert count == 0
    finally:
        await agent1.close()
