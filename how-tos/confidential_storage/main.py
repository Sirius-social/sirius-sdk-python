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


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(run())