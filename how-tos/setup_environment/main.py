import os
import sys
import json
import asyncio

import sirius_sdk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from consts import *


HUB_CONNECTION = AGENT1


async def open_connection():
    is_connected = await sirius_sdk.ping()
    assert is_connected
    print('SDK has connection to Agent')

    my_did = await sirius_sdk.DID.list_my_dids_with_meta()
    print('DID list')
    print(json.dumps(my_did, indent=2))


if __name__ == '__main__':
    sirius_sdk.init(**HUB_CONNECTION)
    asyncio.get_event_loop().run_until_complete(open_connection())
