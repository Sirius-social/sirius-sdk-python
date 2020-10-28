import os
import sys
import json
import asyncio

import sirius_sdk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from consts import *
from utils import join


ME = AGENT1
THEIR = AGENT2


async def their_statically() -> (str, str, str):
    async with sirius_sdk.context(**THEIR):
        did, verkey = await sirius_sdk.DID.create_and_store_my_did()
        endpoints = await sirius_sdk.endpoints()
        simple_endpoint = [e for e in endpoints if e.routing_keys == []][0]
    return did, verkey, simple_endpoint.address


async def their_invitation() -> str:
    async with sirius_sdk.context(**THEIR):
        endpoints = await sirius_sdk.endpoints()
        endpoint = [e for e in endpoints if e.routing_keys == []][0]
        connection_key = await sirius_sdk.Crypto.create_key()

        # Inviter create invitation and publish it for example on Web page via QR code
        # or send via Email
        # Connection key may be used to determine connection context: business-process, web-session, etc.
        invitation = sirius_sdk.aries_rfc.Invitation(
            label='Inviter', endpoint=endpoint.address, recipient_keys=[connection_key]
        )
    return invitation.invitation_url


async def their_dynamically(connection_key: str):
    async with sirius_sdk.context(**THEIR):
        listener = await sirius_sdk.subscribe()
        # Listen only connection requests
        async for event in listener:
            request = event.message
            if isinstance(request, sirius_sdk.aries_rfc.ConnRequest) and event.recipient_verkey == connection_key:
                print('Inviter: Received connection request ==========')
                print(json.dumps(request, indent=2))
                print('================================================')
                # Allocate new DID,Verkey for new connection (you may use const public DID)
                did, verkey = await sirius_sdk.DID.create_and_store_my_did()
                endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0]
                state_machine = sirius_sdk.aries_rfc.Inviter(
                    me=sirius_sdk.Pairwise.Me(did, verkey),
                    connection_key=event.recipient_verkey,  # You may detect use-case by connection-key value
                    my_endpoint=endpoint
                )
                ok, pairwise = await state_machine.create_connection(request)
                assert ok is True
                await sirius_sdk.PairwiseList.ensure_exists(pairwise)
                return


async def me_dynamically(invitation: sirius_sdk.aries_rfc.Invitation) -> sirius_sdk.Pairwise:
    print('Invitee: received invitation =============')
    print(json.dumps(invitation, indent=2))
    print('==========================================')
    async with sirius_sdk.context(**ME):
        # Allocate new did for new connection (you may use const public DID)
        did, verkey = await sirius_sdk.DID.create_and_store_my_did()
        my_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0]
        me = sirius_sdk.Pairwise.Me(did, verkey)
        # Allocate and configure state-machine
        state_machine = sirius_sdk.aries_rfc.Invitee(me, my_endpoint)
        ok, pairwise = await state_machine.create_connection(invitation=invitation, my_label='Invitee')
        assert ok is True
        return pairwise


async def create_statically() -> sirius_sdk.Pairwise:
    async with sirius_sdk.context(**ME):
        # their
        their_did, their_verkey, their_endpoint = await their_statically()
        print(f'Their DID: {their_did}  Verkey: {their_verkey} Endpoint: {their_endpoint}')
        # mine
        my_did, my_verkey = await sirius_sdk.DID.create_and_store_my_did()
        print(f'My DID: {my_did}  Verkey: {my_verkey}')
        # create connection
        connection = sirius_sdk.Pairwise(
            me=sirius_sdk.Pairwise.Me(my_did, my_verkey),
            their=sirius_sdk.Pairwise.Their(their_did, 'My static connection', their_endpoint, their_verkey)
        )
        await sirius_sdk.PairwiseList.create(connection)
        return connection


async def create_dynamically() -> sirius_sdk.Pairwise:
    url = await their_invitation()
    invitation = sirius_sdk.aries_rfc.Invitation.from_url(url)
    assert isinstance(invitation, sirius_sdk.aries_rfc.Invitation)
    # Run inviter and invitee in async thread to emulate independent actors (you mau debug it)
    their_coro = their_dynamically(connection_key=invitation.recipient_keys[0])
    me_coro = me_dynamically(invitation)
    results = await join(their_coro, me_coro)
    pairwise = [item for item in results if isinstance(item, sirius_sdk.Pairwise)][0]
    print('Invitee: established new connection =============')
    print(json.dumps(pairwise.metadata, indent=2))
    print('==========================================')
    return pairwise


if __name__ == '__main__':
    # create Pairwise connection statically
    asyncio.get_event_loop().run_until_complete(create_statically())
    # create Pairwise connection dynamically
    asyncio.get_event_loop().run_until_complete(create_dynamically())
