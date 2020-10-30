import os
import sys
import json
import uuid
import random
import asyncio
from enum import Enum
from typing import List

import sirius_sdk
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.messaging import Message

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from consts import *


BANK = AGENT2
EMPLOYER = AGENT1
DID_EMPLOYER = 'Th7MpTaRZVRYnPiabds81Y'
DID_BANK = 'T8MtAB98aCkgNLtNfQx6WG'
CONN_KEY_BANK = 'Hoq65QDfJZ1G4qUHXMPkmXcA51ztaQsVTEHN8rZFpWjv'
CONN_KEY_EMPLOYER = 'X3huyDF8TmcRr2hRzmyaQH6rqzjFdNy557FBxVXJDpPV4'


def log(message: str):
    print(f'\t{message}')


async def generate_invitations_qr_codes() -> (str, str):
    # BANK
    async with sirius_sdk.context(**BANK):
        try:
            connection_key = await sirius_sdk.Crypto.create_key(seed='0000000000000000SIRIUS_BANK_CONN')
        except sirius_sdk.indy_exceptions.WalletItemAlreadyExists:
            log(f'Bank: conn key {CONN_KEY_BANK} already exists')
        else:
            log(f'Bank: conn key {connection_key} was created')
            assert connection_key == CONN_KEY_BANK
        endpoints = await sirius_sdk.endpoints()
        simple_endpoint = [e for e in endpoints if e.routing_keys == []][0]
        bank_invitation = sirius_sdk.aries_rfc.Invitation(
            label='Sirius Demo bank',
            recipient_keys=[CONN_KEY_BANK],
            endpoint=simple_endpoint.address,
            did=DID_BANK
        )
        log('Bank: invitation')
        log(json.dumps(bank_invitation, indent=2, sort_keys=True))

        # Sirius SDK provide method to generate URL for QR
        # bank_qr_url = await sirius_sdk.generate_qr_code(bank_invitation.invitation_url)

    # EMPLOYER
    async with sirius_sdk.context(**EMPLOYER):
        try:
            connection_key = await sirius_sdk.Crypto.create_key(seed='000000000000SIRIUS_EMPLOYER_CONN')
        except sirius_sdk.indy_exceptions.WalletItemAlreadyExists:
            log(f'Employer: conn key {CONN_KEY_BANK} already exists')
        else:
            log(f'Employer: conn key {connection_key} was created')
            assert connection_key == CONN_KEY_BANK
        endpoints = await sirius_sdk.endpoints()
        simple_endpoint = [e for e in endpoints if e.routing_keys == []][0]
        employer_invitation = sirius_sdk.aries_rfc.Invitation(
            label='Sirius Demo employer',
            recipient_keys=[CONN_KEY_EMPLOYER],
            endpoint=simple_endpoint.address,
            did=DID_EMPLOYER
        )
        log('Employer: invitation')
        log(json.dumps(bank_invitation, indent=2, sort_keys=True))

        # Sirius SDK provide method to generate URL for QR
        # employer_qr_url = await sirius_sdk.generate_qr_code(employer_invitation.invitation_url)

    return 'https://socialsirius.com' + bank_invitation.invitation_url, \
           'https://socialsirius.com' + employer_invitation.invitation_url


async def sirius_bank(network_name: str = 'test_network'):
    async with sirius_sdk.context(**BANK):
        listener = await sirius_sdk.subscribe()
        log('Bank: start to listen events')
        async for event in listener:
            if isinstance(event.message, sirius_sdk.aries_rfc.ConnRequest):
                # Restore invitation request through invitation.connection_key
                # You may use this snippet to encrypt to invitation cookie values for example
                # to link device to browser Web Page
                if event.recipient_verkey == CONN_KEY_BANK:
                    log('Bank: received connection request')
                    
                else:
                    log('Bank: Unknown connection-key')


if __name__ == '__main__':
    qr_bank, qr_employer = asyncio.get_event_loop().run_until_complete(generate_invitations_qr_codes())
    print('invitation URLs')
    print(f'Bank: {qr_bank}')
    print(f'Employer: {qr_employer}')
    print('-------------')
    asyncio.ensure_future(sirius_bank())
    asyncio.get_event_loop().run_forever()
