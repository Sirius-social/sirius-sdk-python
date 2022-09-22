import os
import uuid
import sys
import json
import asyncio

import sirius_sdk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from consts import AGENT1 as CFG


sirius_sdk.init(**CFG)


async def run():
    my_did, my_vk = await sirius_sdk.DID.create_and_store_my_did()
    print("=" * 32)
    inv_url = input('Pass invitation URL here: ')
    p2p = await sirius_sdk.recipes.accept_invitation(
        url=inv_url, me=sirius_sdk.Pairwise.Me(my_did, my_vk), my_label='Confidential Storage Provider'
    )
    print("!" * 32)
    print(f'Connection with "{p2p.their.label}" was established successfully')
    # Authorize with High level of permission
    auth = sirius_sdk.aries_rfc.ConfidentialStorageAuthProvider()
    await auth.authorize(entity=p2p)
    # For example we will provide 2 types of Vaults: encrypted and non-encrypted
    encrypted_mount_to = os.path.join(os.curdir, '.encrypted')
    non_enc_mount_to = os.path.join(os.curdir, '.non_encrypted')
    os.makedirs(encrypted_mount_to)
    os.makedirs(non_enc_mount_to)
    # Create Vaults
    vaults = {
        'encrypted': sirius_sdk.recipes.confidential_storage.SimpleDataVault(
            mounted_dir=encrypted_mount_to, auth=auth
        ),
        'non_encrypted': sirius_sdk.recipes.confidential_storage.SimpleDataVault(
            mounted_dir=non_enc_mount_to, auth=auth
        )
    }
    # Run scheduler
    await sirius_sdk.recipes.confidential_storage.schedule_vaults(
        p2p=p2p, vaults=list(vaults.values())
    )


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(run())