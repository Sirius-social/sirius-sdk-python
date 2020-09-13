import uuid
from datetime import datetime

import pytest

from sirius_sdk import Agent, Pairwise


@pytest.mark.asyncio
async def test_pairwise_list(agent1: Agent, agent2: Agent):
    await agent1.open()
    await agent2.open()
    try:
        did1, verkey1 = await agent1.wallet.did.create_and_store_my_did()
        did2, verkey2 = await agent2.wallet.did.create_and_store_my_did()
        p = Pairwise(
            me=Pairwise.Me(
                did=did1, verkey=verkey1
            ),
            their=Pairwise.Their(
                did=did2, label='Test-Pairwise', endpoint='http://endpoint', verkey=verkey2
            ),
            metadata=dict(test='test-value')
        )

        lst1 = await agent1.wallet.pairwise.list_pairwise()
        await agent1.pairwise_list.ensure_exists(p)
        lst2 = await agent1.wallet.pairwise.list_pairwise()
        assert len(lst1) < len(lst2)

        ok = await agent1.pairwise_list.is_exists(did2)
        assert ok is True

        loaded = await agent1.pairwise_list.load_for_verkey(verkey2)
        assert loaded.metadata == p.metadata
    finally:
        await agent1.close()
        await agent2.close()
