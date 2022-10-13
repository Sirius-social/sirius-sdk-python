import logging
import os
import uuid
import sys
import json
import asyncio

import sirius_sdk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from consts import AGENT1 as CFG


sirius_sdk.init(**CFG)
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__)))
SESSIONS_FILE = os.path.join(BASE, '.session')


async def run():
    # 1. Try to load old session
    p2p = None
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, 'r') as f:
                their_did = f.read()
            p2p = await sirius_sdk.PairwiseList.load_for_did(their_did)
        except:
            logging.exception('Exc')
    if p2p is not None:
        print(f'Do you want to restore old session: "{p2p.their.label}: {p2p.their.did}" ?')
        choice = input('press "yes" if agree: ')
        if choice == 'yes':
            print(f'Session "{p2p.their.did}" was successfully restored')
        else:
            p2p = None

    # 2. Establish connection
    if p2p is None:
        my_did, my_vk = await sirius_sdk.DID.create_and_store_my_did()
        print("=" * 32)
        inv_url = input('Pass invitation URL here: ')
        p2p = await sirius_sdk.recipes.accept_invitation(
            url=inv_url, me=sirius_sdk.Pairwise.Me(my_did, my_vk), my_label='Confidential Storage Provider'
        )
        await sirius_sdk.PairwiseList.ensure_exists(p2p)
        with open(SESSIONS_FILE, 'w+') as f:
            f.truncate(0)
            f.write(p2p.their.did)
        print("!" * 32)
        print(f'Connection with "{p2p.their.label}" was established successfully')
    # Authorize with High level of permission
    auth = sirius_sdk.aries_rfc.ConfidentialStorageAuthProvider()
    await auth.authorize(entity=p2p)
    # For example we will provide 2 types of Vaults: encrypted and non-encrypted
    encrypted_mount_to = os.path.join(os.curdir, '.encrypted')
    non_enc_mount_to = os.path.join(os.curdir, '.non_encrypted')
    if not os.path.exists(encrypted_mount_to):
        os.makedirs(encrypted_mount_to)
    if not os.path.exists(non_enc_mount_to):
        os.makedirs(non_enc_mount_to)
    # Create Vaults
    vault_encrypted = sirius_sdk.recipes.confidential_storage.SimpleDataVault(
        mounted_dir=encrypted_mount_to,
        auth=auth,
        cfg=sirius_sdk.aries_rfc.VaultConfig(
            id=f'did:edvs:{p2p.their.did}#encrypted',
            reference_id='encrypted-vault',
            sequence=1,
            key_agreement=sirius_sdk.aries_rfc.VaultConfig.KeyAgreement(
                id=p2p.me.verkey
            ),
            controller=f'did:peer:{p2p.me.did}',
            delegator=f'did:peer:{p2p.their.did}'
        )
    )
    vault_non_encrypted = sirius_sdk.recipes.confidential_storage.SimpleDataVault(
        mounted_dir=non_enc_mount_to,
        auth=auth,
        cfg=sirius_sdk.aries_rfc.VaultConfig(
            id=f'did:edvs:{p2p.me.did}',
            reference_id='vault',
            sequence=2,
            controller=f'did:peer:{p2p.me.did}',
            delegator=f'did:peer:{p2p.their.did}'
        )
    )
    vault_non_encrypted.cfg.key_agreement = None
    # Run scheduler
    await sirius_sdk.recipes.confidential_storage.schedule_vaults(
        p2p=p2p, vaults=[vault_encrypted, vault_non_encrypted]
    )


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(run())