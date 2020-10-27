import json
import asyncio

import sirius_sdk


HUB_CONNECTION = {
    'server_uri': 'https://demo.socialsirius.com',
    'credentials': 'ez8ucxfrTiV1hPX99MHt/C/MUJCo8OmN4AMVmddE/sew8gBzsOg040FWBSXzHd9hDoj5B5KN4aaLiyzTqkrbD3uaeSwmvxVsqkC0xl5dtIc='.encode(),
    'p2p': sirius_sdk.P2PConnection(
            my_keys=('6QvQ3Y5pPMGNgzvs86N3AQo98pF5WrzM1h6WkKH3dL7f', '28Au6YoU7oPt6YLpbWkzFryhaQbfAcca9KxZEmz22jJaZoKqABc4UJ9vDjNTtmKSn2Axfu8sT52f5Stmt7JD4zzh'),
            their_verkey='Dc85FszkSDcwwYPy8CaveMJqsRvTvZgZ5Q4coaPYpW4k'
        )
}


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
