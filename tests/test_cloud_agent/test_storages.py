import uuid

import pytest

from sirius_sdk import Agent
from sirius_sdk.agent.storages import InWalletImmutableCollection


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
