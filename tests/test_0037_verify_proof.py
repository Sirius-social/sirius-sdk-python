import uuid
import json
from typing import List
from datetime import datetime

import pytest

import sirius_sdk
from sirius_sdk import Agent, Pairwise
from sirius_sdk.agent.codec import encode
from sirius_sdk.agent.aries_rfc.utils import str_to_utc
from sirius_sdk.agent.ledger import CredentialDefinition
from sirius_sdk.agent.aries_rfc.feature_0037_present_proof.state_machines import Verifier, Prover, \
    AttribTranslation, RequestPresentationMessage
from sirius_sdk.agent.aries_rfc.feature_0037_present_proof.interactive import SelfIdentity
from sirius_sdk.errors.indy_exceptions import AnoncredsMasterSecretDuplicateNameError

from .conftest import get_pairwise
from .helpers import run_coroutines, IndyAgent, ServerTestSuite


async def run_verifier(
        uri: str, credentials: bytes, p2p: sirius_sdk.P2PConnection,
        prover: Pairwise, proof_request: dict, translation: List[AttribTranslation] = None
) -> (bool, dict):
    try:
        async with sirius_sdk.context(uri, credentials, p2p):
            ledger = await sirius_sdk.ledger('default')
            machine = Verifier(prover=prover, ledger=ledger)
            success = await machine.verify(
                proof_request, translation=translation, comment='I am Verifier', proto_version='1.0'
            )
            if not success:
                print('===================== Verifier terminated with error ====================')
                if machine.problem_report:
                    print(json.dumps(machine.problem_report, indent=2, sort_keys=True))
                print('=======================================================================')
                return False, None
            return success, machine.revealed_attrs or machine.problem_report
    except Exception as e:
        print('==== Verifier routine Exception: ' + repr(e))
        raise


async def run_prover(
        uri: str, credentials: bytes, p2p: sirius_sdk.P2PConnection,
        verifier: Pairwise, master_secret_id: str, self_attested_identity: dict = None
):
    async with sirius_sdk.context(uri, credentials, p2p):
        listener = await sirius_sdk.subscribe()
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
            ledger = await sirius_sdk.ledger('default')
            machine = Prover(verifier=verifier, ledger=ledger, time_to_live=ttl, self_attested_identity=self_attested_identity)
            success = await machine.prove(request, master_secret_id)
            if not success:
                print('===================== Prover terminated with error ====================')
                if machine.problem_report:
                    print(json.dumps(machine.problem_report, indent=2, sort_keys=True))
                print('=======================================================================')
            return success, machine.problem_report
        except Exception as e:
            print('==== Prover routine Exception: ' + repr(e))
            raise


async def run_prover_interactive(
        uri: str, credentials: bytes, p2p: sirius_sdk.P2PConnection,
        verifier: Pairwise, master_secret_id: str, self_attested_identity: dict = None
):
    async with sirius_sdk.context(uri, credentials, p2p):
        listener = await sirius_sdk.subscribe()
        event = await listener.get_one()
        assert event.pairwise is not None
        assert event.pairwise.their.did == verifier.their.did
        request = event.message
        assert isinstance(request, RequestPresentationMessage)
        ttl = 60
        try:
            ledger = await sirius_sdk.ledger('default')
            machine = Prover(verifier=verifier, ledger=ledger, time_to_live=ttl, self_attested_identity=self_attested_identity)
            async with machine.prove_interactive(master_secret_id):
                print('')
                identity = await machine.interactive.fetch(request)
                print('')
                success, problem_report = await machine.interactive.prove(identity)
                if not success:
                    print('===================== Prover terminated with error ====================')
                    if problem_report:
                        print(json.dumps(problem_report, indent=2, sort_keys=True))
                    print('=======================================================================')
                return success, problem_report
        except Exception as e:
            print('==== Prover routine Exception: ' + repr(e))
            raise


@pytest.mark.asyncio
async def test_sane(
        test_suite: ServerTestSuite, agent1: Agent, agent2: Agent, agent3: Agent, prover_master_secret_name: str
):
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
        try:
            await prover.wallet.anoncreds.prover_create_master_secret(prover_master_secret_name)
        except AnoncredsMasterSecretDuplicateNameError:
            pass

        prover_secret_id = prover_master_secret_name
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

    finally:
        await issuer.close()
        await prover.close()
        await verifier.close()

    prover = test_suite.get_agent_params('agent2')
    verifier = test_suite.get_agent_params('agent3')

    # FIRE !!!
    attr_referent_id = 'attr1_referent'
    pred_referent_id = 'predicate1_referent'
    async with sirius_sdk.context(verifier['server_address'], verifier['credentials'], verifier['p2p']):
        proof_request = {
            "nonce": await sirius_sdk.AnonCreds.generate_nonce(),
            "name": "Test ProofRequest",
            "version": "0.1",
            "requested_attributes": {
                attr_referent_id: {
                    "name": "attr1",
                    "restrictions": {
                        "issuer_did": did_issuer,
                        'cred_def_id': cred_def.id
                    }
                }
            },
            "requested_predicates": {
                pred_referent_id: {
                    'name': 'attr2',
                    'p_type': '>=',
                    'p_value': 100,
                    "restrictions": {
                        "issuer_did": did_issuer,
                        'cred_def_id': cred_def.id
                    }
                }
            }
        }

    coro_verifier = run_verifier(
        verifier['server_address'], verifier['credentials'], verifier['p2p'],
        prover=v2p,
        proof_request=proof_request
    )
    coro_prover = run_prover(
        prover['server_address'], prover['credentials'], prover['p2p'],
        verifier=p2v,
        master_secret_id=prover_secret_id
    )
    print('Run state machines')
    results = await run_coroutines(coro_verifier, coro_prover, timeout=60)
    print('Finish state machines')
    print(str(results))
    assert len(results) == 2
    for res, data in results:
        assert res is True


@pytest.mark.asyncio
async def test_multiple_provers(
    test_suite: ServerTestSuite,
    agent1: Agent, agent2: Agent, agent3: Agent, agent4: Agent, prover_master_secret_name: str
):
    issuer = agent1
    prover1 = agent2
    verifier = agent3
    prover2 = agent4
    await issuer.open()
    await prover1.open()
    await prover2.open()
    await verifier.open()
    try:
        print('Establish pairwises')
        i_to_p1 = await get_pairwise(issuer, prover1)
        i_to_p2 = await get_pairwise(issuer, prover2)
        p1_to_i = await get_pairwise(prover1, issuer)
        p2_to_i = await get_pairwise(prover2, issuer)
        v_to_p1 = await get_pairwise(verifier, prover1)
        v_to_p2 = await get_pairwise(verifier, prover2)
        p1_to_v = await get_pairwise(prover1, verifier)
        p2_to_v = await get_pairwise(prover2, verifier)

        print('Register schema')
        did_issuer, verkey_issuer = i_to_p1.me.did, i_to_p1.me.verkey
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

        print('Prepare Provers')
        for prover in [prover1, prover2]:
            try:
                await prover.wallet.anoncreds.prover_create_master_secret(prover_master_secret_name)
            except AnoncredsMasterSecretDuplicateNameError:
                pass

        cred_ids = {
            0: 'cred-id-' + uuid.uuid4().hex,
            1: 'cred-id-' + uuid.uuid4().hex
        }
        prover_did = {
            0: p1_to_i.me.did,
            1: p2_to_i.me.did
        }
        for i, prover in enumerate([prover1, prover2]):
            prover_secret_id = prover_master_secret_name
            cred_values = {'attr1': f'Value-{i}', 'attr2': 200 + i*10, 'attr3': i*1.5}
            cred_id = cred_ids[0]

            # Issue credential
            offer = await issuer.wallet.anoncreds.issuer_create_credential_offer(cred_def_id=cred_def.id)
            cred_request, cred_metadata = await prover.wallet.anoncreds.prover_create_credential_req(
                prover_did=prover_did[i], cred_offer=offer, cred_def=cred_def.body, master_secret_id=prover_secret_id
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

    finally:
        await issuer.close()
        await prover1.close()
        await prover2.close()
        await verifier.close()

    prover1 = test_suite.get_agent_params('agent2')
    verifier = test_suite.get_agent_params('agent3')
    prover2 = test_suite.get_agent_params('agent4')
    # FIRE !!!
    attr_referent_id = 'attr1_referent'
    pred_referent_id = 'predicate1_referent'
    async with sirius_sdk.context(verifier['server_address'], verifier['credentials'], verifier['p2p']):
        proof_request = {
            "nonce": await sirius_sdk.AnonCreds.generate_nonce(),
            "name": "Test ProofRequest",
            "version": "0.1",
            "requested_attributes": {
                attr_referent_id: {
                    "name": "attr1",
                    "restrictions": {
                        "issuer_did": did_issuer,
                        'cred_def_id': cred_def.id
                    }
                }
            },
            "requested_predicates": {
                pred_referent_id: {
                    'name': 'attr2',
                    'p_type': '>=',
                    'p_value': 100,
                    "restrictions": {
                        "issuer_did": did_issuer,
                        'cred_def_id': cred_def.id
                    }
                }
            }
        }

    for prover, v2p, p2v in [(prover1, v_to_p1, p1_to_v), (prover2, v_to_p2, p2_to_v)]:
        coro_verifier = run_verifier(
            verifier['server_address'], verifier['credentials'], verifier['p2p'],
            prover=v2p,
            proof_request=proof_request
        )
        coro_prover = run_prover(
            prover['server_address'], prover['credentials'], prover['p2p'],
            verifier=p2v,
            master_secret_id=prover_master_secret_name
        )
        print('Run state machines')
        results = await run_coroutines(coro_verifier, coro_prover, timeout=60)
        print('Finish state machines')
        print(str(results))
        assert len(results) == 2
        for res, data in results:
            assert res is True


@pytest.mark.asyncio
async def test_self_attested_attribs(test_suite: ServerTestSuite,
    agent1: Agent, agent2: Agent, agent3: Agent, agent4: Agent, prover_master_secret_name: str
):
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
        try:
            await prover.wallet.anoncreds.prover_create_master_secret(prover_master_secret_name)
        except AnoncredsMasterSecretDuplicateNameError:
            pass

        prover_secret_id = prover_master_secret_name
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

    finally:
        await issuer.close()
        await prover.close()
        await verifier.close()

    prover = test_suite.get_agent_params('agent2')
    verifier = test_suite.get_agent_params('agent3')

    # FIRE !!!
    attr1_referent_id = 'attr1_referent'
    attr2_referent_id = 'attr2_referent'
    attr3_referent_id = 'attr3_referent'
    async with sirius_sdk.context(verifier['server_address'], verifier['credentials'], verifier['p2p']):
        proof_request = {
            "nonce": await sirius_sdk.AnonCreds.generate_nonce(),
            "name": "Test ProofRequest",
            "version": "0.1",
            "requested_attributes": {
                attr1_referent_id: {
                    "name": "attr1",
                    "restrictions": [{
                        "issuer_did": did_issuer,
                        'cred_def_id': cred_def.id
                    }]
                },
                attr2_referent_id: {
                    "name": "first_name"
                },
                attr3_referent_id: {
                    "name": "email"
                }
            }
        }

    coro_verifier = run_verifier(
        verifier['server_address'], verifier['credentials'], verifier['p2p'],
        prover=v2p,
        proof_request=proof_request
    )
    coro_prover = run_prover(
        prover['server_address'], prover['credentials'], prover['p2p'],
        verifier=p2v,
        master_secret_id=prover_secret_id,
        self_attested_identity={'email': 'test@gmail.com'}
    )
    print('Run state machines')
    results = await run_coroutines(coro_verifier, coro_prover, timeout=60)
    print('Finish state machines')
    print(str(results))
    assert len(results) == 2
    for res, data in results:
        assert res is True
    revealed_attrs = [d for _, d in results if d][0]
    # Asserts
    assert revealed_attrs['attr1'] == 'Value-1'  # cred value
    assert revealed_attrs['first_name'] == ''  # empty str
    assert revealed_attrs['email'] == 'test@gmail.com'  # was set via self_attested_attrs


@pytest.mark.asyncio
async def test_self_identity(
        test_suite: ServerTestSuite,
        agent1: Agent, agent2: Agent, agent3: Agent, prover_master_secret_name: str
):
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
        print('Register schema')
        did_issuer, verkey_issuer = i2p.me.did, i2p.me.verkey
        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, anoncred_schema = await issuer.wallet.anoncreds.issuer_create_schema(
            did_issuer, schema_name, '1.0', ['attr1', 'attr2', 'age']
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
        try:
            await prover.wallet.anoncreds.prover_create_master_secret(prover_master_secret_name)
        except AnoncredsMasterSecretDuplicateNameError:
            pass
        prover_secret_id = prover_master_secret_name

        cred_count = 3
        for n in range(cred_count):
            # Issue credential
            cred_values = {'attr1': f'Value[{n}]', 'attr2': n, 'age': 100}
            cred_id = f'cred-id-{uuid.uuid4().hex}-{n}'

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

        prover_sdk = test_suite.get_agent_params('agent2')
        verifier_sdk = test_suite.get_agent_params('agent3')

        # FIRE !!!
        attr1_referent_id = 'attr1_referent'
        attr2_referent_id = 'attr2_referent'
        attr3_referent_id = 'attr3_referent'
        pred_referent_id = 'pred1_referent'
        async with sirius_sdk.context(verifier_sdk['server_address'], verifier_sdk['credentials'], verifier_sdk['p2p']):
            proof_request = {
                "nonce": await sirius_sdk.AnonCreds.generate_nonce(),
                "name": "Test ProofRequest",
                "version": "0.1",
                "requested_attributes": {
                    attr1_referent_id: {
                        "name": "attr1",
                        "restrictions": [{
                            "issuer_did": did_issuer,
                            'cred_def_id': cred_def.id
                        }]
                    },
                    attr2_referent_id: {
                        "name": "attr2",
                        "restrictions": [{
                            "issuer_did": did_issuer,
                            'cred_def_id': cred_def.id
                        }]
                    },
                    attr3_referent_id: {
                        "name": "email",
                        "restrictions": []
                    }
                },
                "requested_predicates": {
                    pred_referent_id: {
                        'name': 'age',
                        'p_type': '>=',
                        'p_value': 0,
                        "restrictions": {
                            "issuer_did": did_issuer,
                            'cred_def_id': cred_def.id
                        }
                    }
                }
            }
        print('')
        async with sirius_sdk.context(prover_sdk['server_address'], prover_sdk['credentials'], prover_sdk['p2p']):
            self_identity = SelfIdentity()
            await self_identity.load(
                self_attested_identity={'email': 'my@mail.com'},
                proof_request=proof_request,
                limit_referents=cred_count-1
            )
            # self-attested
            assert self_identity.self_attested_attributes[attr3_referent_id].name == 'email'
            assert self_identity.self_attested_attributes[attr3_referent_id].value == 'my@mail.com'
            # requested attributes
            assert len(self_identity.requested_attributes[attr1_referent_id]) == 2
            assert len(self_identity.requested_attributes[attr2_referent_id]) == 2
            assert self_identity.requested_attributes[attr1_referent_id][0].revealed is True

            assert self_identity.requested_attributes[attr1_referent_id][0].is_selected is True
            assert self_identity.requested_attributes[attr1_referent_id][1].is_selected is False
            assert self_identity.requested_attributes[attr2_referent_id][0].is_selected is True
            assert self_identity.requested_attributes[attr2_referent_id][1].is_selected is False
            self_identity.requested_attributes[attr1_referent_id][1].is_selected = True
            assert self_identity.requested_attributes[attr1_referent_id][0].is_selected is False
            assert self_identity.requested_attributes[attr1_referent_id][1].is_selected is True
            # requested predicates
            assert len(self_identity.requested_predicates[pred_referent_id]) == 2
            assert self_identity.requested_predicates[pred_referent_id][0].revealed is False
            assert self_identity.requested_predicates[pred_referent_id][0].is_selected is True
            assert self_identity.requested_predicates[pred_referent_id][1].is_selected is False
    finally:
        await issuer.close()
        await prover.close()
        await verifier.close()


@pytest.mark.asyncio
async def test_prove_interactive(
        test_suite: ServerTestSuite,
        agent1: Agent, agent2: Agent, agent3: Agent, prover_master_secret_name: str
):
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
        schema_id, anoncred_schema = await issuer.wallet.anoncreds.issuer_create_schema(
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
        try:
            await prover.wallet.anoncreds.prover_create_master_secret(prover_master_secret_name)
        except AnoncredsMasterSecretDuplicateNameError:
            pass
        prover_secret_id = prover_master_secret_name

        # Issue credential
        cred_values = {'attr1': f'Value', 'attr2': 123, 'attr3': 100.5}
        cred_id = f'cred-id-{uuid.uuid4().hex}'

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

        prover_sdk = test_suite.get_agent_params('agent2')
        verifier_sdk = test_suite.get_agent_params('agent3')

        # FIRE !!!
        attr1_referent_id = 'attr1_referent'
        attr2_referent_id = 'attr2_referent'
        async with sirius_sdk.context(verifier_sdk['server_address'], verifier_sdk['credentials'], verifier_sdk['p2p']):
            proof_request = {
                "nonce": await sirius_sdk.AnonCreds.generate_nonce(),
                "name": "Test ProofRequest",
                "version": "0.1",
                "requested_attributes": {
                    attr1_referent_id: {
                        "name": "attr1",
                        "restrictions": [{
                            "issuer_did": did_issuer,
                            'cred_def_id': cred_def.id
                        }]
                    },
                    attr2_referent_id: {
                        "name": "email"
                    }
                }
            }

        prover_sdk = test_suite.get_agent_params('agent2')
        verifier_sdk = test_suite.get_agent_params('agent3')

        coro_verifier = run_verifier(
            verifier_sdk['server_address'], verifier_sdk['credentials'], verifier_sdk['p2p'],
            prover=v2p,
            proof_request=proof_request
        )
        coro_prover = run_prover_interactive(
            prover_sdk['server_address'], prover_sdk['credentials'], prover_sdk['p2p'],
            verifier=p2v,
            master_secret_id=prover_secret_id,
            self_attested_identity={'email': 'test@gmail.com'}
        )
        print('Run state machines')
        results = await run_coroutines(coro_verifier, coro_prover, timeout=60)
        print('Finish state machines')
        print(str(results))
        assert len(results) == 2
        for res, data in results:
            assert res is True
        revealed_attrs = [d for _, d in results if d][0]
        assert revealed_attrs['email'] == 'test@gmail.com'
        assert revealed_attrs['attr1'] == 'Value'
    finally:
        await issuer.close()
        await prover.close()
        await verifier.close()
