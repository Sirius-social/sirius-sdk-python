import json
from urllib.parse import urlparse, urlunparse

import pytest

import sirius_sdk
from sirius_sdk.agent.connections import Endpoint
from sirius_sdk.agent.aries_rfc.feature_0160_connection_protocol.state_machines import Inviter, Invitee, \
    ConnRequest, Invitation

from .helpers import run_coroutines, IndyAgent, ServerTestSuite


def replace_url_components(url: str, base: str = None) -> str:
    ret = url
    if base:
        parsed = urlparse(url)
        components = list(parsed)
        components[1] = urlparse(base).netloc
        ret = urlunparse(components)
    return ret


async def read_events(uri: str, credentials: bytes, p2p: sirius_sdk.P2PConnection):
    async with sirius_sdk.context(uri, credentials, p2p):
        listener = await sirius_sdk.subscribe()
        async for event in listener:
            print('========= EVENT ============')
            print(json.dumps(event, indent=2, sort_keys=True))
            print('============================')


async def run_inviter(
        uri: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, expected_connection_key: str,
        me: sirius_sdk.Pairwise.Me = None, replace_endpoints: bool = False
):
    async with sirius_sdk.context(uri, credentials, p2p):
        endpoints_ = await sirius_sdk.endpoints()
        my_endpoint = [e for e in endpoints_ if e.routing_keys == []][0]
        if replace_endpoints:
            new_address = replace_url_components(my_endpoint.address, pytest.test_suite_overlay_address)
            my_endpoint = Endpoint(new_address, my_endpoint.routing_keys, is_default=my_endpoint.is_default)
        listener = await sirius_sdk.subscribe()
        async for event in listener:
            connection_key = event['recipient_verkey']
            if expected_connection_key == connection_key:
                request = event['message']
                assert isinstance(request, ConnRequest)
                if replace_endpoints:
                    request['connection']['did_doc']['service'][0]['serviceEndpoint'] = replace_url_components(
                        request['connection']['did_doc']['service'][0]['serviceEndpoint'],
                        pytest.old_agent_overlay_address
                    )
                # Setup state machine
                if me is None:
                    my_did, my_verkey = await sirius_sdk.DID.create_and_store_my_did()
                    me = sirius_sdk.Pairwise.Me(did=my_did, verkey=my_verkey)
                # create connection
                machine = Inviter(me, connection_key, my_endpoint)
                ok, pairwise = await machine.create_connection(request)
                assert ok is True
                await sirius_sdk.PairwiseList.ensure_exists(pairwise)
        pass


async def run_invitee(
        uri: str, credentials: bytes, p2p: sirius_sdk.P2PConnection,
        invitation: Invitation, my_label: str, me: sirius_sdk.Pairwise.Me = None, replace_endpoints: bool = False
):
    async with sirius_sdk.context(uri, credentials, p2p):
        if me is None:
            my_did, my_verkey = await sirius_sdk.DID.create_and_store_my_did()
            me = sirius_sdk.Pairwise.Me(did=my_did, verkey=my_verkey)
        endpoints_ = await sirius_sdk.endpoints()
        my_endpoint = [e for e in endpoints_ if e.routing_keys == []][0]
        if replace_endpoints:
            new_address = replace_url_components(my_endpoint.address, pytest.test_suite_overlay_address)
            my_endpoint = Endpoint(new_address, my_endpoint.routing_keys, is_default=my_endpoint.is_default)
            new_address = replace_url_components(invitation['serviceEndpoint'], pytest.old_agent_overlay_address)
            invitation['serviceEndpoint'] = new_address
        # Create and start machine
        machine = Invitee(me, my_endpoint)
        ok, pairwise = await machine.create_connection(invitation=invitation, my_label=my_label)
        assert ok is True
        await sirius_sdk.PairwiseList.ensure_exists(pairwise)


@pytest.mark.asyncio
async def test_establish_connection(test_suite: ServerTestSuite):
    inviter = test_suite.get_agent_params('agent1')
    invitee = test_suite.get_agent_params('agent2')

    # Get endpoints
    async with sirius_sdk.context(inviter['server_address'], inviter['credentials'], inviter['p2p']):
        inviter_endpoint_address = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
        connection_key = await sirius_sdk.Crypto.create_key()
        invitation = Invitation(label='Inviter', endpoint=inviter_endpoint_address, recipient_keys=[connection_key])

    # Init Me
    async with sirius_sdk.context(inviter['server_address'], inviter['credentials'], inviter['p2p']):
        did, verkey = await sirius_sdk.DID.create_and_store_my_did()
        inviter_me = sirius_sdk.Pairwise.Me(did, verkey)
    async with sirius_sdk.context(invitee['server_address'], invitee['credentials'], invitee['p2p']):
        did, verkey = await sirius_sdk.DID.create_and_store_my_did()
        invitee_me = sirius_sdk.Pairwise.Me(did, verkey)

    await run_coroutines(
        run_inviter(
            inviter['server_address'], inviter['credentials'], inviter['p2p'], connection_key, inviter_me
        ),
        run_invitee(
            invitee['server_address'], invitee['credentials'], invitee['p2p'], invitation, 'Invitee', invitee_me
        )
    )

    # Check for Inviter
    async with sirius_sdk.context(inviter['server_address'], inviter['credentials'], inviter['p2p']):
        pairwise = await sirius_sdk.PairwiseList.load_for_verkey(invitee_me.verkey)
        assert pairwise is not None
        assert pairwise.their.did == invitee_me.did
    # Check for Invitee
    async with sirius_sdk.context(invitee['server_address'], invitee['credentials'], invitee['p2p']):
        pairwise = await sirius_sdk.PairwiseList.load_for_verkey(inviter_me.verkey)
        assert pairwise is not None
        assert pairwise.their.did == inviter_me.did


@pytest.mark.asyncio
async def test_update_pairwise_metadata(test_suite: ServerTestSuite):
    inviter = test_suite.get_agent_params('agent1')
    invitee = test_suite.get_agent_params('agent2')

    # Get endpoints
    async with sirius_sdk.context(inviter['server_address'], inviter['credentials'], inviter['p2p']):
        inviter_endpoint_address = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
        connection_key = await sirius_sdk.Crypto.create_key()
        invitation = Invitation(label='Inviter', endpoint=inviter_endpoint_address, recipient_keys=[connection_key])
    async with sirius_sdk.context(invitee['server_address'], invitee['credentials'], invitee['p2p']):
        invitee_endpoint_address = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address

    # Init Me
    async with sirius_sdk.context(inviter['server_address'], inviter['credentials'], inviter['p2p']):
        did, verkey = await sirius_sdk.DID.create_and_store_my_did()
        inviter_side = sirius_sdk.Pairwise.Me(did, verkey)
    async with sirius_sdk.context(invitee['server_address'], invitee['credentials'], invitee['p2p']):
        did, verkey = await sirius_sdk.DID.create_and_store_my_did()
        invitee_side = sirius_sdk.Pairwise.Me(did, verkey)
    # Manually set pairwise list
    async with sirius_sdk.context(inviter['server_address'], inviter['credentials'], inviter['p2p']):
        await sirius_sdk.DID.store_their_did(invitee_side.did, invitee_side.verkey)
        p = sirius_sdk.Pairwise(
            me=inviter_side,
            their=sirius_sdk.Pairwise.Their(
                invitee_side.did, 'Invitee', invitee_endpoint_address, invitee_side.verkey
            )
        )
        await sirius_sdk.PairwiseList.create(p)
    async with sirius_sdk.context(invitee['server_address'], invitee['credentials'], invitee['p2p']):
        await sirius_sdk.DID.store_their_did(inviter_side.did, inviter_side.verkey)
        p = sirius_sdk.Pairwise(
            me=invitee_side,
            their=sirius_sdk.Pairwise.Their(
                inviter_side.did, 'Inviter', inviter_endpoint_address, inviter_side.verkey
            )
        )
        await sirius_sdk.PairwiseList.create(p)

    await run_coroutines(
        run_inviter(
            inviter['server_address'], inviter['credentials'], inviter['p2p'], connection_key, inviter_side
        ),
        run_invitee(
            invitee['server_address'], invitee['credentials'], invitee['p2p'], invitation, 'Invitee', invitee_side
        )
    )

    # Check for Inviter
    async with sirius_sdk.context(inviter['server_address'], inviter['credentials'], inviter['p2p']):
        pairwise = await sirius_sdk.PairwiseList.load_for_did(invitee_side.did)
        assert pairwise.metadata != {}
        assert pairwise.metadata is not None

    # Check for Invitee
    async with sirius_sdk.context(invitee['server_address'], invitee['credentials'], invitee['p2p']):
        pairwise = await sirius_sdk.PairwiseList.load_for_did(inviter_side.did)
        assert pairwise.metadata != {}
        assert pairwise.metadata is not None


@pytest.mark.asyncio
async def test_invitee_back_compatibility(indy_agent: IndyAgent, test_suite: ServerTestSuite):
    their_invitaton = await indy_agent.create_invitation(label='Test Invitee')
    invitation = Invitation.from_url(their_invitaton['url'])
    invitee = test_suite.get_agent_params('agent1')

    # Init invitee
    async with sirius_sdk.context(invitee['server_address'], invitee['credentials'], invitee['p2p']):
        did, verkey = await sirius_sdk.DID.create_and_store_my_did()
        invitee_side = sirius_sdk.Pairwise.Me(did, verkey)

    await run_coroutines(
        run_invitee(
            invitee['server_address'], invitee['credentials'], invitee['p2p'], invitation, 'Invitee', invitee_side, True
        ),
        read_events(
            invitee['server_address'], invitee['credentials'], invitee['p2p']
        )
    )
    invitation_pairwise = None
    async with sirius_sdk.context(invitee['server_address'], invitee['credentials'], invitee['p2p']):
        async for i, pairwise in sirius_sdk.PairwiseList.enumerate():
            if pairwise.me.did == invitee_side.did:
                invitation_pairwise = pairwise
                break
    assert invitation_pairwise is not None


@pytest.mark.asyncio
async def test_inviter_back_compatibility(indy_agent: IndyAgent, test_suite: ServerTestSuite, agent1: sirius_sdk.Agent):
    inviter = test_suite.get_agent_params('agent1')
    # Init inviter
    async with sirius_sdk.context(inviter['server_address'], inviter['credentials'], inviter['p2p']):
        inviter_endpoint_address = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
        connection_key = await sirius_sdk.Crypto.create_key()
        inviter_endpoint_address = replace_url_components(inviter_endpoint_address, pytest.test_suite_overlay_address)
        invitation = Invitation(label='Inviter', endpoint=inviter_endpoint_address, recipient_keys=[connection_key])
        invitation_url = invitation.invitation_url
        did, verkey = await sirius_sdk.DID.create_and_store_my_did()
        inviter_side = sirius_sdk.Pairwise.Me(did, verkey)

    await run_coroutines(
        run_inviter(
            inviter['server_address'], inviter['credentials'], inviter['p2p'], connection_key, inviter_side, True
        ),
        indy_agent.invite(invitation_url=invitation_url),
    )

    invitated_pairwise = None
    async with sirius_sdk.context(inviter['server_address'], inviter['credentials'], inviter['p2p']):
        async for i, p in sirius_sdk.PairwiseList.enumerate():
            assert isinstance(p, sirius_sdk.Pairwise)
            if p.me.did == inviter_side.did:
                invitated_pairwise = p
                break
    assert invitated_pairwise is not None
