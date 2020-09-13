import uuid

import pytest

from sirius_sdk.errors.exceptions import BaseSiriusException
from sirius_sdk import Agent, Pairwise
from sirius_sdk.agent.aries_rfc.feature_0048_trust_ping import Ping

from .helpers import run_coroutines, IndyAgent


@pytest.mark.asyncio
async def test_establish_connection(agent1: Agent, agent2: Agent, agent3: Agent):
    await agent1.open()
    await agent2.open()
    await agent3.open()
    try:
        did1, verkey1 = await agent1.wallet.did.create_and_store_my_did()
        did2, verkey2 = await agent2.wallet.did.create_and_store_my_did()
        endpoint_address_2 = [e for e in agent2.endpoints if e.routing_keys == []][0].address
        endpoint_address_3 = [e for e in agent3.endpoints if e.routing_keys == []][0].address

        await agent1.wallet.did.store_their_did(did2, verkey2)
        await agent1.wallet.pairwise.create_pairwise(did2, did1)
        await agent2.wallet.did.store_their_did(did1, verkey1)
        await agent2.wallet.pairwise.create_pairwise(did1, did2)

        to = Pairwise(
            me=Pairwise.Me(did=did1, verkey=verkey1),
            their=Pairwise.Their(did=did2, label='Agent2', endpoint=endpoint_address_2, verkey=verkey2)
        )
        listener2 = await agent2.subscribe()
        ping = Ping(comment=uuid.uuid4().hex)

        # Check OK
        await agent1.send_to(ping, to)
        event = await listener2.get_one()
        recv = event.message
        assert isinstance(recv, Ping)
        assert recv.comment == ping.comment

        # Check ERR
        to = Pairwise(
            me=Pairwise.Me(did=did1, verkey=verkey1),
            their=Pairwise.Their(did=did2, label='Agent3', endpoint=endpoint_address_3, verkey=verkey2)
        )
        with pytest.raises(BaseSiriusException):
            await agent1.send_to(ping, to)

    finally:
        await agent1.close()
        await agent2.close()
        await agent3.close()
