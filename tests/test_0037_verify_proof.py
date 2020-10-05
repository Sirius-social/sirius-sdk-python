import uuid
from typing import List
from datetime import datetime

import pytest

from sirius_sdk import Agent, Pairwise
from sirius_sdk.agent.codec import encode
from sirius_sdk.agent.aries_rfc.utils import str_to_utc
from sirius_sdk.agent.ledger import CredentialDefinition
from sirius_sdk.agent.aries_rfc.feature_0037_present_proof import Verifier, Prover, AttribTranslation, \
    RequestPresentationMessage
from sirius_sdk.errors.indy_exceptions import AnoncredsMasterSecretDuplicateNameError

from .conftest import get_pairwise
from .helpers import run_coroutines, IndyAgent


async def run_verifier(
        agent: Agent, prover: Pairwise, proof_request: dict, translation: List[AttribTranslation] = None
) -> bool:
    try:
        machine = Verifier(prover=prover, pool_name='default', transports=agent)
        success = await machine.verify(proof_request, translation=translation, comment='I am Verifier')
        return success
    except Exception as e:
        print('==== Verifier routine Exception: ' + repr(e))


async def run_prover(agent: Agent, verifier: Pairwise, master_secret_id: str):
    listener = await agent.subscribe()
    event = await listener.get_one()
    assert event.pairwise is not None
    assert event.pairwise.their.did == verifier.their.did
    request = event.message
    assert isinstance(request, RequestPresentationMessage)
    ttl = 60
    if request.expires_time:
        expire = str_to_utc(request.expires_time, raise_exceptions=False)
        delta = expire - datetime.utcnow()
        if delta.seconds > 0:
            ttl = delta.seconds
    try:
        machine = Prover(verifier=verifier, pool_name='default', transports=agent, time_to_live=ttl)
        success = await machine.prove(request, master_secret_id)
        return success
    except Exception as e:
        print('==== Prover routine Exception: ' + repr(e))


@pytest.mark.asyncio
async def test_sane(agent1: Agent, agent2: Agent, agent3: Agent):
    issuer = agent1
    prover = agent2
    verifier = agent3
    await issuer.open()
    await prover.open()
    await verifier.open()
    try:
        print('Establish pairwises')
        i2p = await get_pairwise(issuer, prover)
        p2i = await get_pairwise(prover, issuer)
        v2p = await get_pairwise(verifier, prover)
        p2v = await get_pairwise(prover, verifier)

        print('Register schema')
        did_issuer, verkey_issuer = i2p.me.did, i2p.me.verkey
        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, anoncred_schema = await agent1.wallet.anoncreds.issuer_create_schema(
            did_issuer, schema_name, '1.0', ['attr1', 'attr2', 'attr3']
        )
        ledger = issuer.ledger('default')
        ok, schema = await ledger.register_schema(schema=anoncred_schema, submitter_did=did_issuer)
        assert ok is True

        print('Register credential def')
        ok, cred_def = await ledger.register_cred_def(
            cred_def=CredentialDefinition(tag='TAG', schema=schema),
            submitter_did=did_issuer
        )
        assert ok is True

        print('Prepare Prover')
        master_secret_name = 'prover_master_secret_name'
        try:
            await prover.wallet.anoncreds.prover_create_master_secret(master_secret_name)
        except AnoncredsMasterSecretDuplicateNameError:
            pass

        prover_secret_id = master_secret_name
        cred_values = {'attr1': 'Value-1', 'attr2': 456, 'attr3': 5.87}
        cred_id = 'cred-id-' + uuid.uuid4().hex

        # Issue credential
        offer = await issuer.wallet.anoncreds.issuer_create_credential_offer(cred_def_id=cred_def.id)
        cred_request, cred_metadata = await prover.wallet.anoncreds.prover_create_credential_req(
            prover_did=p2i.me.did, cred_offer=offer, cred_def=cred_def.body, master_secret_id=prover_secret_id
        )
        encoded_cred_values = dict()
        for key, value in cred_values.items():
            encoded_cred_values[key] = dict(raw=str(value), encoded=encode(value))
        ret = await issuer.wallet.anoncreds.issuer_create_credential(
            cred_offer=offer,
            cred_req=cred_request,
            cred_values=encoded_cred_values,
            rev_reg_id=None,
            blob_storage_reader_handle=None
        )
        cred, cred_revoc_id, revoc_reg_delta = ret
        await prover.wallet.anoncreds.prover_store_credential(
            cred_req_metadata=cred_metadata,
            cred=cred,
            cred_def=cred_def.body,
            rev_reg_def=None,
            cred_id=cred_id
        )

        # FIRE !!!
        attr_referent_id = 'attr1_referent'
        pred_referent_id = 'predicate1_referent'
        proof_request = {
            "nonce": await verifier.wallet.anoncreds.generate_nonce(),
            "name": "Test ProofRequest",
            "version": "0.1",
            "requested_attributes": {
                attr_referent_id: {
                    "name": "attr1",
                    "restrictions": {
                        "issuer_did": did_issuer
                    }
                }
            },
            "requested_predicates": {
                pred_referent_id: {
                    'name': 'attr2',
                    'p_type': '>=',
                    'p_value': 100,
                    "restrictions": {
                        "issuer_did": did_issuer
                    }
                }
            }
        }

        coro_verifier = run_verifier(
            agent=verifier,
            prover=v2p,
            proof_request=proof_request
        )
        coro_prover = run_prover(
            agent=prover,
            verifier=p2v,
            master_secret_id=prover_secret_id
        )
        print('Run state machines')
        results = await run_coroutines(coro_verifier, coro_prover, timeout=60)
        print('Finish state machines')
        print(str(results))
        assert len(results) == 2
        for res in results:
            assert res is True

    finally:
        await issuer.close()
        await prover.close()
        await verifier.close()


@pytest.mark.asyncio
async def test_back_compatibility(agent1: Agent, agent2: Agent, agent3: IndyAgent):
    issuer = agent1
    prover = agent3
    verifier = agent2
    await issuer.open()
    await verifier.open()
    try:
        pass
    finally:
        await issuer.close()
        await verifier.close()
