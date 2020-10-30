import os
import uuid
import sys
import json
import asyncio

import sirius_sdk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from consts import *
from helpers import establish_connection


ISSUER = AGENT1
VERIFIER = AGENT3
PROVER = AGENT4

# Issuer has Public DID
ISSUER_DID = 'Th7MpTaRZVRYnPiabds81Y'
# for demo purposes verifier and prover has public did too for simple code
# but in real world it is not True for every case
VERIFIER_DID = 'LnXR1rPnncTPZvRdmJKhJQ'
PROVER_DID = 'PNQm3CwyXbN5e39Rw3dXYx'


def log(message: str):
    print(f'\t{message}')


async def ensure_cred_def_exists_in_dkms(network_name: str) -> (sirius_sdk.Schema, sirius_sdk.CredentialDefinition):
    async with sirius_sdk.context(**ISSUER):
        dkms = await sirius_sdk.ledger(network_name)  # Test network is prepared for Demo purposes
        schema_id, anon_schema = await sirius_sdk.AnonCreds.issuer_create_schema(
            ISSUER_DID, 'Live_demo_schema', '1.0', ['first_name', 'last_name', 'age']
        )
        # Ensure schema exists on DKMS
        schema_ = await dkms.ensure_schema_exists(anon_schema, ISSUER_DID)
        # Ensure CredDefs is stored to DKMS
        cred_def_fetched = await dkms.fetch_cred_defs(tag='TAG', schema_id=schema_.id)
        if cred_def_fetched:
            cred_def_ = cred_def_fetched[0]
        else:
            ok, cred_def_ = await dkms.register_cred_def(
                cred_def=sirius_sdk.CredentialDefinition(tag='TAG', schema=schema_),
                submitter_did=ISSUER_DID
            )
            assert ok is True
        return schema_, cred_def_


async def issue_credential(
        schema: sirius_sdk.Schema, cred_def: sirius_sdk.CredentialDefinition,
        first_name: str, last_name: str, age: int,
        prover: sirius_sdk.Pairwise, cred_id: str = None
):
    async with sirius_sdk.context(**ISSUER):
        feature_0036 = sirius_sdk.aries_rfc.Issuer(holder=prover)
        log('Issuer: start issuing...')
        success = await feature_0036.issue(
            values={'first_name': first_name, 'last_name': last_name, 'age': age},
            schema=schema,
            cred_def=cred_def,
            comment='Hello, it is your Transcript',
            cred_id=cred_id or f'cred-id-' + uuid.uuid4().hex
        )
        if success:
            log('Issuer: issuing finished successfully')
        else:
            log('Issuer: issuing finished with ERROR')
            if feature_0036.problem_report:
                log('Issuer problem report:')
                log(json.dumps(feature_0036.problem_report, indent=2, sort_keys=True))
        return success


async def verify_credential(prover: sirius_sdk.Pairwise, network_name: str, proof_request: dict):
    async with sirius_sdk.context(**VERIFIER):
        if 'nonce' not in proof_request:
            proof_request['nonce'] = await sirius_sdk.AnonCreds.generate_nonce()
        log('Verifier: start verify...')
        dkms = await sirius_sdk.ledger(network_name)
        feature_0037 = sirius_sdk.aries_rfc.Verifier(
            prover=prover,
            ledger=dkms
        )
        success = await feature_0037.verify(proof_request)
        if success:
            log('Verifier: verification finished successfully')
            log('presented revealed part of credentials')
            log(json.dumps(
                feature_0037.requested_proof['revealed_attrs'], indent=8
            ))
        else:
            log('Verifier: verification with ERROR')
            if feature_0037.problem_report:
                log('Issuer problem report:')
                log(json.dumps(feature_0037.problem_report, indent=2, sort_keys=True))
        return success


async def prover_in_background(network_name: str):
    async with sirius_sdk.context(**PROVER):
        try:
            await sirius_sdk.AnonCreds.prover_create_master_secret(PROVER_SECRET_ID)
        except sirius_sdk.indy_exceptions.AnoncredsMasterSecretDuplicateNameError:
            # ignore
            pass
        reactor = await sirius_sdk.subscribe()
        log('Prover: start listening income requests')
        dkms = await sirius_sdk.ledger(network_name)
        async for event in reactor:
            if isinstance(event.message, sirius_sdk.aries_rfc.OfferCredentialMessage):
                offer: sirius_sdk.aries_rfc.OfferCredentialMessage = event.message
                log('Prover: received credential offer')
                # Accept all incoming credentials for DEMO purpose
                issuer: sirius_sdk.Pairwise = event.pairwise
                feature_0036 = sirius_sdk.aries_rfc.Holder(issuer)
                log('Prover: start to process offer...')
                success, cred_id = await feature_0036.accept(offer=offer, master_secret_id=PROVER_SECRET_ID)
                if success:
                    log(f'Prover: credential with cred-id: {cred_id} successfully stored to Wallet')
                else:
                    log(f'Prover: credential was not stored due to some problems')
                    if feature_0036.problem_report:
                        log('Prover: problem report:')
                        log(json.dumps(feature_0036.problem_report, indent=2, sort_keys=True))
            elif isinstance(event.message, sirius_sdk.aries_rfc.RequestPresentationMessage):
                proof_request: sirius_sdk.aries_rfc.RequestPresentationMessage = event.message
                log('Prover: received proof request')
                # Accept all incoming proof-requests for DEMO purpose
                verifier: sirius_sdk.Pairwise = event.pairwise
                log('Prover: start to verify...')
                feature_0037 = sirius_sdk.aries_rfc.Prover(
                    verifier=verifier,
                    ledger=dkms
                )
                success = await feature_0037.prove(request=proof_request, master_secret_id=PROVER_SECRET_ID)
                if success:
                    log(f'Prover: credentials was successfully proved')
                else:
                    log(f'Prover: credential was not proved')
                    if feature_0037.problem_report:
                        log('Prover: problem report:')
                        log(json.dumps(feature_0036.problem_report, indent=2, sort_keys=True))


if __name__ == '__main__':
    # Prepared Test DKMS network
    network_name = 'test_network'
    # Establish Cyber-security relationships
    issuer_p2p_prover = establish_connection(ISSUER, ISSUER_DID, PROVER, PROVER_DID)
    prover_p2p_issuer = establish_connection(PROVER, PROVER_DID, ISSUER, ISSUER_DID)
    verifier_p2p_prover = establish_connection(VERIFIER, VERIFIER_DID, PROVER, PROVER_DID)
    prover_p2p_verifier = establish_connection(PROVER, PROVER_DID, VERIFIER, VERIFIER_DID)
    # Allocate Credential definition
    schema_dkms, cred_def_dkms = asyncio.get_event_loop().run_until_complete(ensure_cred_def_exists_in_dkms(
        network_name=network_name
    ))
    # Run prover in background
    tsk_prover = asyncio.ensure_future(prover_in_background(
        network_name=network_name
    ))
    asyncio.get_event_loop().run_until_complete(issue_credential(
        schema=schema_dkms,
        cred_def=cred_def_dkms,
        first_name='Han',
        last_name='Solo',
        age=22,
        prover=issuer_p2p_prover
    ))
    verify_ok = asyncio.get_event_loop().run_until_complete(
        verify_credential(
            prover=verifier_p2p_prover,
            network_name=network_name,
            proof_request={
                "name": "Demo Proof Request",
                "version": "0.1",
                "requested_attributes": {
                    'attr1_referent': {
                        "name": "first_name",
                        "restrictions": {
                            "issuer_did": ISSUER_DID
                        }
                    },
                    'attr2_referent': {
                        "name": "last_name",
                        "restrictions": {
                            "issuer_did": ISSUER_DID
                        }
                    },
                    'attr3_referent': {
                        "name": "age",
                        "restrictions": {
                            "issuer_did": ISSUER_DID
                        }
                    }
                }
            }
        )
    )
    if verify_ok:
        print('Demo OK')
    else:
        print('Demo ERROR!')
