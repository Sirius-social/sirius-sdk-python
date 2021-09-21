import uuid
from typing import List, Any
from datetime import datetime, timedelta

import pytest

import sirius_sdk
from sirius_sdk.agent.wallet import NYMRole
from sirius_sdk.agent.aries_rfc.utils import str_to_utc
from sirius_sdk.agent.ledger import Schema, CredentialDefinition
from sirius_sdk.agent.aries_rfc.feature_0036_issue_credential.state_machines import Issuer, Holder, \
    AttribTranslation, ProposedAttrib, OfferCredentialMessage
from sirius_sdk.errors.indy_exceptions import AnoncredsMasterSecretDuplicateNameError

from .conftest import get_pairwise
from .helpers import run_coroutines, IndyAgent, ServerTestSuite


async def run_issuer(
        uri: str, credentials: bytes, p2p: sirius_sdk.P2PConnection,
        holder: sirius_sdk.Pairwise, values: dict, schema: Schema, cred_def: CredentialDefinition,
        preview: List[ProposedAttrib] = None, translation: List[AttribTranslation] = None, cred_id: str = None
):
    async with sirius_sdk.context(uri, credentials, p2p):
        machine = Issuer(holder=holder)
        success = await machine.issue(
            values=values,
            schema=schema,
            cred_def=cred_def,
            comment='Hello Iam issuer',
            preview=preview,
            translation=translation,
            cred_id=cred_id
        )
        return success


async def run_holder(
        uri: str, credentials: bytes, p2p: sirius_sdk.P2PConnection,
        issuer: sirius_sdk.Pairwise, master_secret_id: str
):
    async with sirius_sdk.context(uri, credentials, p2p):
        listener = await sirius_sdk.subscribe()
        event = await listener.get_one()
        assert event.pairwise is not None
        offer = event.message
        assert isinstance(offer, OfferCredentialMessage)
        ttl = 60
        if offer.expires_time:
            expire = str_to_utc(offer.expires_time, raise_exceptions=False)
            delta = expire - datetime.utcnow()
            if delta.seconds > 0:
                ttl = delta.seconds
        machine = Holder(issuer=issuer, time_to_live=ttl)
        success, cred_id = await machine.accept(offer, master_secret_id, comment='Hello, Iam holder')
        return success, cred_id


async def run_issuer_indy_agent(
        indy_agent: IndyAgent, cred_def_id: str, cred_def: dict, values: dict, their_did: str,
        issuer_schema: dict = None, preview: List[ProposedAttrib] = None, translation: List[AttribTranslation] = None,
        rev_reg_id: str = None, cred_id: str = None, ttl: int = 60
) -> bool:
    log = await indy_agent.issue_credential(
        cred_def_id, cred_def, values, their_did, 'Test issuer', None, issuer_schema, preview, translation,
        rev_reg_id, cred_id, ttl
    )
    if len(log) > 2:
        last = log[-1]['message']
        pred = log[-2]['message']
        return ('Received ACK' in pred) and ('Done' in last)
    else:
        return False


@pytest.mark.asyncio
async def test_sane(
        test_suite: ServerTestSuite, agent1: sirius_sdk.Agent, agent2: sirius_sdk.Agent, prover_master_secret_name: str
):
    issuer = agent1
    holder = agent2
    await issuer.open()
    await holder.open()
    try:
        i2h = await get_pairwise(issuer, holder)
        h2i = await get_pairwise(holder, issuer)

        did_issuer, verkey_issuer = i2h.me.did, i2h.me.verkey
        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, anoncred_schema = await agent1.wallet.anoncreds.issuer_create_schema(
            did_issuer, schema_name, '1.0', ['attr1', 'attr2', 'attr3', 'attr4']
        )
        ledger = issuer.ledger('default')
        ok, schema = await ledger.register_schema(schema=anoncred_schema, submitter_did=did_issuer)
        assert ok is True

        ok, cred_def = await ledger.register_cred_def(
            cred_def=CredentialDefinition(tag='TAG', schema=schema),
            submitter_did=did_issuer
        )
        assert ok is True

        print('Prepare Holder')
        try:
            await holder.wallet.anoncreds.prover_create_master_secret(prover_master_secret_name)
        except AnoncredsMasterSecretDuplicateNameError:
            pass
    finally:
        await issuer.close()
        await holder.close()

    issuer = test_suite.get_agent_params('agent1')
    holder = test_suite.get_agent_params('agent2')
    holder_secret_id = prover_master_secret_name

    cred_id = 'cred-id-' + uuid.uuid4().hex
    coro_issuer = run_issuer(
        issuer['server_address'], issuer['credentials'], issuer['p2p'],
        holder=i2h,
        values={'attr1': 'Value-1', 'attr2': 567, 'attr3': 5.7, 'attr4': 'base64'},
        preview=[ProposedAttrib(name="attr1", value="Value-1", mime_type="text/plain"),
                 ProposedAttrib(name="attr4", value="base64", mime_type="image/png")],
        schema=schema, cred_def=cred_def, cred_id=cred_id
    )
    coro_holder = run_holder(
        holder['server_address'], holder['credentials'], holder['p2p'],
        issuer=h2i,
        master_secret_id=holder_secret_id
    )

    results = await run_coroutines(coro_issuer, coro_holder, timeout=60)
    cred_id = None
    for res in results:
        if type(res) is tuple:
            ok, cred_id = res
        else:
            ok = res
        assert ok is True

    assert cred_id is not None
    async with sirius_sdk.context(holder['server_address'], holder['credentials'], holder['p2p']):
        cred = await sirius_sdk.AnonCreds.prover_get_credential(cred_id)
        assert cred
        mime_types = await Holder.get_mime_types(cred_id)
        assert len(mime_types) == 2
        assert mime_types["attr1"] == "text/plain"
        assert mime_types["attr4"] == "image/png"


@pytest.mark.asyncio
async def test_issuer_back_compatibility(indy_agent: IndyAgent, test_suite: ServerTestSuite, agent1: sirius_sdk.Agent):
    issuer = agent1
    await issuer.open()
    try:
        endpoint_issuer = [e for e in issuer.endpoints if e.routing_keys == []][0].address
        did_issuer, verkey_issuer = await issuer.wallet.did.create_and_store_my_did()
        did_holder, verkey_holder = await indy_agent.create_and_store_my_did()
        pairwise_for_issuer = sirius_sdk.Pairwise(
            me=sirius_sdk.Pairwise.Me(did_issuer, verkey_issuer),
            their=sirius_sdk.Pairwise.Their(did_holder, 'Holder', indy_agent.endpoint['url'], verkey_holder)
        )
        pairwise_for_holder = sirius_sdk.Pairwise(
            me=sirius_sdk.Pairwise.Me(did_holder, verkey_holder),
            their=sirius_sdk.Pairwise.Their(did_issuer, 'Issuer', endpoint_issuer, verkey_issuer)
        )
        pairwise_for_issuer.their.netloc = pytest.old_agent_overlay_address.replace('http://', '')
        pairwise_for_holder.their.netloc = pytest.test_suite_overlay_address.replace('http://', '')
        await indy_agent.create_pairwise_statically(pairwise_for_holder)
        await issuer.wallet.did.store_their_did(did_holder, verkey_holder)
        await issuer.pairwise_list.ensure_exists(pairwise_for_issuer)

        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, anoncred_schema = await agent1.wallet.anoncreds.issuer_create_schema(
            did_issuer, schema_name, '1.0', ['attr1', 'attr2', 'attr3']
        )
        ledger = issuer.ledger('default')
        ok, resp = await issuer.wallet.ledger.write_nym(
            'default', 'Th7MpTaRZVRYnPiabds81Y', did_issuer, verkey_issuer, 'Issuer', NYMRole.TRUST_ANCHOR
        )
        assert ok is True
        ok, schema = await ledger.register_schema(schema=anoncred_schema, submitter_did=did_issuer)
        assert ok is True

        ok, cred_def = await ledger.register_cred_def(
            cred_def=CredentialDefinition(tag='TAG', schema=schema),
            submitter_did=did_issuer
        )
        assert ok is True
    finally:
        await issuer.close()

    issuer = test_suite.get_agent_params('agent1')
    cred_id = 'cred-id-' + uuid.uuid4().hex
    coro_issuer = run_issuer(
        issuer['server_address'], issuer['credentials'], issuer['p2p'],
        holder=pairwise_for_issuer,
        values={'attr1': 'Value-1', 'attr2': 567, 'attr3': 5.7},
        schema=schema, cred_def=cred_def, cred_id=cred_id
    )
    results = await run_coroutines(coro_issuer, timeout=60)
    assert len(results) == 1
    assert results[0] is True


@pytest.mark.asyncio
async def test_holder_back_compatibility(
        indy_agent: IndyAgent, agent1: sirius_sdk.Agent,
        test_suite: ServerTestSuite, prover_master_secret_name: str
):
    holder = agent1
    await holder.open()
    try:
        endpoint_holder = [e for e in holder.endpoints if e.routing_keys == []][0].address
        did_issuer, verkey_issuer = await indy_agent.create_and_store_my_did()
        did_holder, verkey_holder = await holder.wallet.did.create_and_store_my_did()
        pairwise_for_issuer = sirius_sdk.Pairwise(
            me=sirius_sdk.Pairwise.Me(did_issuer, verkey_issuer),
            their=sirius_sdk.Pairwise.Their(did_holder, 'Holder', endpoint_holder, verkey_holder)
        )
        pairwise_for_holder = sirius_sdk.Pairwise(
            me=sirius_sdk.Pairwise.Me(did_holder, verkey_holder),
            their=sirius_sdk.Pairwise.Their(did_issuer, 'Issuer', indy_agent.endpoint['url'], verkey_issuer)
        )
        pairwise_for_issuer.their.netloc = pytest.test_suite_overlay_address.replace('http://', '')
        pairwise_for_holder.their.netloc = pytest.old_agent_overlay_address.replace('http://', '')
        await indy_agent.create_pairwise_statically(pairwise_for_issuer)
        await holder.wallet.did.store_their_did(did_issuer, verkey_issuer)
        await holder.pairwise_list.ensure_exists(pairwise_for_holder)

        ok, resp = await agent1.wallet.ledger.write_nym(
            'default', 'Th7MpTaRZVRYnPiabds81Y', did_issuer, verkey_issuer, 'Issuer', NYMRole.TRUST_ANCHOR
        )
        assert ok is True
        # Register schema
        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, schema = await indy_agent.register_schema(did_issuer, schema_name, '1.0', ['attr1', 'attr2', 'attr3'])
        cred_def_id, cred_def = await indy_agent.register_cred_def(did_issuer, schema_id, 'TAG')

        print('Prepare Holder')
        try:
            await holder.wallet.anoncreds.prover_create_master_secret(prover_master_secret_name)
        except AnoncredsMasterSecretDuplicateNameError:
            pass
    finally:
        await holder.close()

    holder = test_suite.get_agent_params('agent1')
    holder_secret_id = prover_master_secret_name
    cred_id = 'cred-id-' + uuid.uuid4().hex

    coro_issuer = run_issuer_indy_agent(
        indy_agent=indy_agent, cred_def_id=cred_def_id, cred_def=cred_def,
        values={'attr1': 'Value-1', 'attr2': 567, 'attr3': 5.7},
        their_did=pairwise_for_issuer.their.did,
        issuer_schema=schema, rev_reg_id=None,
        cred_id=cred_id
    )
    coro_holder = run_holder(
        holder['server_address'], holder['credentials'], holder['p2p'],
        issuer=pairwise_for_holder,
        master_secret_id=holder_secret_id
    )

    results = await run_coroutines(coro_issuer, coro_holder, timeout=60)
    assert len(results) == 2

    for res in results:
        if type(res) is tuple:
            ok, cred_id = res
        else:
            ok = res
        assert ok is True

    assert cred_id is not None
    async with sirius_sdk.context(holder['server_address'], holder['credentials'], holder['p2p']):
        cred = await sirius_sdk.AnonCreds.prover_get_credential(cred_id)
    assert cred
