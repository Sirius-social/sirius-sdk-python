import asyncio
import datetime
import uuid
from typing import List, Dict

import sirius_sdk
from sirius_sdk.agent.consensus.simple import MicroLedgerSimpleConsensus, ProposeTransactionsMessage
from sirius_sdk.agent.microledgers.abstract import Transaction
from sirius_sdk.base import AbstractStateMachine


STEWARD = {
    'sdk': {
        'server_uri': 'https://demo.socialsirius.com',
        'credentials': 'ez8ucxfrTiV1hPX99MHt/C/MUJCo8OmN4AMVmddE/sew8gBzsOg040FWBSXzHd9hDoj5B5KN4aaLiyzTqkrbD3uaeSwmvxVsqkC0xl5dtIc='.encode(),
        'p2p': sirius_sdk.P2PConnection(
            my_keys=('6QvQ3Y5pPMGNgzvs86N3AQo98pF5WrzM1h6WkKH3dL7f', '28Au6YoU7oPt6YLpbWkzFryhaQbfAcca9KxZEmz22jJaZoKqABc4UJ9vDjNTtmKSn2Axfu8sT52f5Stmt7JD4zzh'),
            their_verkey='6oczQNLU7bSBzVojkGsfAv3CbXagx7QLUL7Yj1Nba9iw'
        )
    },
    'alias': 'Steward',
    'did': 'Th7MpTaRZVRYnPiabds81Y',
    'verkey': '"FYmoFw55GeQH7SRFa37dkx1d2dZ3zUF8ckg7wmL7ofN4',
    'endpoint': None
}

LABORATORY = {
    'sdk': {
        'server_uri': 'https://demo.socialsirius.com',
        'credentials': 'BXXwMmUlw7MTtVWhcVvbSVWbC1GopGXDuo+oY3jHkP/4jN3eTlPDwSwJATJbzwuPAAaULe6HFEP5V57H6HWNqYL4YtzWCkW2w+H7fLgrfTLaBtnD7/P6c5TDbBvGucOV'.encode(),
        'p2p': sirius_sdk.P2PConnection(
            my_keys=('EzJKT2Q6Cw8pwy34xPa9m2qPCSvrMmCutaq1pPGBQNCn', '273BEpAM8chzfMBDSZXKhRMPPoaPRWRDtdMmNoKLmJUU6jvm8Nu8caa7dEdcsvKpCTHmipieSsatR4aMb1E8hQAa'),
            their_verkey='342Bm3Eq9ruYfvHVtLxiBLLFj54Tq6p8Msggt7HiWxBt'
        )
    },
    'alias': 'Laboratory',
    'did': 'X1YdguoHBaY1udFQMbbKKG',
    'verkey': 'HMf57wiWK1FhtzLbm76o37tEMJvaCbWfGsaUzCZVZwnT',
    'endpoint': 'https://demo.socialsirius.com/endpoint/b14bc782806c4c298b56e38d79fb51e9'
}

AIR_COMPANY = {
    'sdk': {
        'server_uri': 'https://demo.socialsirius.com',
        'credentials': '/MYok4BSllG8scfwXVVRK8V47I1PC44mktwiJKKduf38Yb7UgIsq8n4SXVBrRwIzHMQA/6sdiKgrB20Kbw9ieHbOGlxx3UVlWNM0Xfc9Rgk85cCLSHWM2vqlNQSGwHAM+udXpuPwAkfKjiUtzyPBcA=='.encode(),
        'p2p': sirius_sdk.P2PConnection(
            my_keys=('BhDMxfvhc2PZ4BpGTExyWHYkJDFPhmXpaRvUoCoNJ8rL', '2wwakvFwBRWbFeLyDbsH6cYVve6FBH6DL133sPNN87jWYbc6rHXj7Q3dnAsbB6EuNwquucsDzSBhNcpxgyVLCCYg'),
            their_verkey='8VNHw79eMTZJBasgjzdwyKyCYA88ajm9gvP98KGcjaBt'
        )
    },
    'alias': 'AirCompany',
    'did': 'XwVCkzM6sMxk87M2GKtya6',
    'verkey': 'Hs4FPfB1d7nFUcqbMZqofFg4qoeGxGThmSbunJYpVAM6',
    'endpoint': 'https://demo.socialsirius.com/endpoint/7d4b74435ca34efeb600537cde08186d'
}

AIRPORT = {
    'sdk': {
        'server_uri': 'https://demo.socialsirius.com',
        'credentials': '/MYok4BSllG8scfwXVVRK3NATRRtESRnhUHOU3nJxxZ+gg81/srwEPNWfZ+3+6GaEHcqghOJvRoV7taA/vCd2+q2hIEpDO/yCPfMr4x2K0vC/pom1gFRJwJAKI3LpMy3'.encode(),
        'p2p': sirius_sdk.P2PConnection(
            my_keys=('HBEe9KkPCK4D1zs6UBzLqWp6j2Gj88zy3miqybvYx42p', '23jutNJBbgn8bbX53Qr36JSeS2VtZHvY4DMqazXHq6mDEPNkuA3FkKVGAMJdjPznfizLg9nh448DXZ7e1724qk1a'),
            their_verkey='BNxpmTgs9B3yMURa1ta7avKuBA5wcBp5ZmXfqPFPYGAP'
        )
    },
    'alias': 'Airport',
    'did': 'Ap29nQ3Kf2bGJdWEV3m4AG',
    'verkey': '6M8qgMdkqGzQ2yhryV3F9Kvk785qAFny5JuLp1CJCcHW',
    'endpoint': 'https://demo.socialsirius.com/endpoint/68bec29ce63240bc9981f0d8759ec5f2'
}

DKMS_NAME = 'test_network'
COVID_MICROLEDGER_NAME = "covid_ledger_test3"


class Laboratory:

    def __init__(self, hub_credentials: dict, pairwises: List[sirius_sdk.Pairwise], me: sirius_sdk.Pairwise.Me):
        self.hub_credentials: dict = hub_credentials
        self.pairwises: List[sirius_sdk.Pairwise] = pairwises
        self.me: sirius_sdk.Pairwise.Me = me
        self.covid_microledger_participants = [me.did] + [pw.their.did for pw in pairwises]

    async def listen(self):
        listener = await sirius_sdk.subscribe()
        async for event in listener:
            if isinstance(event.message, ProposeTransactionsMessage):
                machine = MicroLedgerSimpleConsensus(self.me)
                await machine.accept_commit(event.pairwise, event.message)

    async def issue_test_results(self, cred_def: sirius_sdk.CredentialDefinition, schema: sirius_sdk.Schema, test_results: dict):
        async with sirius_sdk.context(**self.hub_credentials):
            connection_key = await sirius_sdk.Crypto.create_key()
            endpoints = await sirius_sdk.endpoints()
            simple_endpoint = [e for e in endpoints if e.routing_keys == []][0]
            invitation = sirius_sdk.aries_rfc.Invitation(
                label="Invitation to connect with medical organization",
                recipient_keys=[connection_key],
                endpoint=simple_endpoint.address
            )

            qr_content = invitation.invitation_url
            qr_url = await sirius_sdk.generate_qr_code(qr_content)

            print("Scan this QR by Sirius App for receiving the Covid test result " + qr_url)

            listener = await sirius_sdk.subscribe()
            async for event in listener:
                if event.recipient_verkey == connection_key and isinstance(event.message, sirius_sdk.aries_rfc.ConnRequest):
                    request: sirius_sdk.aries_rfc.ConnRequest = event.message
                    my_did, my_verkey = await sirius_sdk.DID.create_and_store_my_did()
                    sm = sirius_sdk.aries_rfc.Inviter(
                        me=sirius_sdk.Pairwise.Me(
                            did=my_did,
                            verkey=my_verkey
                        ),
                        connection_key=connection_key,
                        my_endpoint=simple_endpoint
                    )
                    # Run state-machine procedure
                    success, p2p = await sm.create_connection(request)
                    if success:
                        message = sirius_sdk.aries_rfc.Message(
                            content="Hello!!!" + str(datetime.datetime.now()),
                            locale="en"
                        )
                        print(message)
                        await sirius_sdk.send_to(message, p2p)

                        issuer = sirius_sdk.aries_rfc.Issuer(p2p)
                        cred_id = "cred-id-" + uuid.uuid4().hex
                        preview = [sirius_sdk.aries_rfc.ProposedAttrib(key, value) for key, value in test_results.values()]
                        translation = [
                            sirius_sdk.aries_rfc.AttribTranslation("full_name", "Patient Full Name"),
                            sirius_sdk.aries_rfc.AttribTranslation("location", "Patient location"),
                            sirius_sdk.aries_rfc.AttribTranslation("bio_location", "Biomaterial sampling point"),
                            sirius_sdk.aries_rfc.AttribTranslation("timestamp", "Timestamp"),
                            sirius_sdk.aries_rfc.AttribTranslation("approved", "Laboratory specialist"),
                            sirius_sdk.aries_rfc.AttribTranslation("has_covid", "Covid test result")
                        ]
                        ok = await issuer.issue(
                            values=test_results,
                            schema=schema,
                            cred_def=cred_def,
                            preview=preview,
                            translation=translation,
                            comment="Here is your covid test results",
                            locale="en"
                        )
                        if ok:
                            print("Covid test confirmation was successfully issued")
                            if test_results["has_covid"]:
                                ledger = await sirius_sdk.Microledgers.ledger(COVID_MICROLEDGER_NAME)
                                machine = MicroLedgerSimpleConsensus(self.me)
                                tr = Transaction({
                                    "test_res": test_results
                                })
                                await machine.commit(ledger, self.covid_microledger_participants, [tr])

                    break




async def create_med_creds(issuer_did: str) -> (sirius_sdk.CredentialDefinition, sirius_sdk.Schema):
    schema_name = "Covid test result 2"
    schema_id, anon_schema = await sirius_sdk.AnonCreds.issuer_create_schema(issuer_did, schema_name, '1.0',
                                         ["approved", "timestamp", "bio_location", "location", "full_name", "has_covid"])
    l = await sirius_sdk.ledger(DKMS_NAME)
    schema = await l.ensure_schema_exists(anon_schema, issuer_did)
    if not schema:
        ok, schema = await l.register_schema(anon_schema, issuer_did)
        if ok:
            print("Covid test result registered successfully")
        else:
            print("Covid test result was not registered")
            return None, None

    else:
        print("Med schema is exists in the ledger")

    ok, cred_def = await l.register_cred_def(
        cred_def=sirius_sdk.CredentialDefinition(tag='TAG', schema=schema),
        submitter_did=issuer_did)

    if not ok:
        print("Cred def was not registered")

    return cred_def, schema





async def initialize():
    async with sirius_sdk.context(**LABORATORY['sdk']):
        cred_def, schema = await create_med_creds(LABORATORY['did'])
        test_res = {
            "approved": "House M.D.",
            "timestamp": str(datetime.datetime.now()),
            "bio_location": "Nur-Sultan",
            "location": "Nur-Sultan",
            "full_name": "Mike",
            "sars_cov_2_igm": False,
            "sars_cov_2_igg": False
        }
        await process_medical(cred_def, schema, test_res)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(initialize())