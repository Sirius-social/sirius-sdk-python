import pytest

from sirius_sdk import Agent, Pairwise
from sirius_sdk.agent.aries_rfc.feature_0160_connection_protocol import *

from .helpers import run_coroutines


async def run_inviter(agent: Agent, expected_connection_key: str, me: Pairwise.Me=None):
    my_endpoint = [e for e in agent.endpoints if e.routing_keys == []][0]
    listener = await agent.subscribe()
    async for event in listener:
        connection_key = event['recipient_verkey']
        if expected_connection_key == connection_key:
            request = event['message']
            assert isinstance(request, ConnRequest)
            # Setup state machine
            machine = Inviter(agent)
            if me is None:
                my_did, my_verkey = await agent.wallet.did.create_and_store_my_did()
                me = Pairwise.Me(did=my_did, verkey=my_verkey)
            # create connection
            ok, pairwise = await machine.create_connection(me, connection_key, request, my_endpoint)
            assert ok is True
            await agent.wallet.pairwise.create_pairwise(
                their_did=pairwise.their.did,
                my_did=pairwise.me.did,
                metadata=pairwise.metadata
            )
    pass


async def run_invitee(agent: Agent, invitation: Invitation, my_label: str, me: Pairwise.Me=None):
    if me is None:
        my_did, my_verkey = await agent.wallet.did.create_and_store_my_did()
        me = Pairwise.Me(did=my_did, verkey=my_verkey)
    my_endpoint = [e for e in agent.endpoints if e.routing_keys == []][0]
    # Create and start machine
    machine = Invitee(agent)
    ok, pairwise = await machine.create_connection(
        me=me, invitation=invitation, my_label=my_label, my_endpoint=my_endpoint
    )
    assert ok is True
    await agent.wallet.pairwise.create_pairwise(
        their_did=pairwise.their.did,
        my_did=pairwise.me.did,
        metadata=pairwise.metadata
    )


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
        # Init Me
        did, verkey = await inviter.wallet.did.create_and_store_my_did()
        inviter_me = Pairwise.Me(did, verkey)
        did, verkey = await invitee.wallet.did.create_and_store_my_did()
        invitee_me = Pairwise.Me(did, verkey)

        await run_coroutines(
            run_inviter(inviter, connection_key, inviter_me),
            run_invitee(invitee, invitation, 'Invitee', invitee_me)
        )

        # Check for Inviter
        pairwise = await inviter.wallet.pairwise.get_pairwise(invitee_me.did)
        assert pairwise['my_did'] == inviter_me.did
        # Check for Invitee
        pairwise = await invitee.wallet.pairwise.get_pairwise(inviter_me.did)
        assert pairwise['my_did'] == invitee_me.did

    finally:
        await inviter.close()
        await invitee.close()
