import pytest

from sirius_sdk import Agent, TheirEndpoint, Pairwise
from sirius_sdk.agent.aries_rfc.feature_0160_connection_protocol import *

from .helpers import run_coroutines


async def run_inviter(agent: Agent, expected_connection_key: str):
    my_endpoint = [e for e in agent.endpoints if e.routing_keys == []][0]
    listener = await agent.subscribe()
    async for event in listener:
        connection_key = event['recipient_verkey']
        if expected_connection_key == connection_key:
            request = event['message']
            assert isinstance(request, ConnRequest)
            # Create new DID for pairwise connection
            my_did, my_verkey = await agent.wallet.did.create_and_store_my_did()
            # Setup state machine
            machine = Inviter(agent)
            me = Pairwise.Me(did=my_did, verkey=my_verkey)
            # Start state machine
            await machine.create_connection(me, connection_key, request, my_endpoint)
            print('!')
    print('!')


async def run_invitee(agent: Agent, invitation: Invitation, my_label: str):
    # Create new DID for pairwise connection
    my_did, my_verkey = await agent.wallet.did.create_and_store_my_did()
    my_endpoint = [e for e in agent.endpoints if e.routing_keys == []][0]
    # Create and start machine
    machine = Invitee(agent)
    me = Pairwise.Me(did=my_did, verkey=my_verkey)
    await machine.create_connection(
        me=me, invitation=invitation, my_label=my_label, my_endpoint=my_endpoint
    )
    print('!')


@pytest.mark.asyncio
async def test_establish_connection(agent1: Agent, agent2: Agent):
    inviter = agent1
    invitee = agent2
    await inviter.open()
    await invitee.open()
    try:
        # Get endpoints
        inviter_endpoint_address = [e for e in inviter.endpoints if e.routing_keys == []][0].address
        connection_key = await inviter.wallet.crypto.create_key()
        invitation = Invitation(label='Inviter', endpoint=inviter_endpoint_address, recipient_keys=[connection_key])

        await run_coroutines(
            run_inviter(inviter, connection_key),
            run_invitee(invitee, invitation, 'Invitee')
        )

    finally:
        await inviter.close()
        await invitee.close()