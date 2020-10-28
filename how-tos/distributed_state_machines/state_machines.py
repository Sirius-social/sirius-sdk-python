import json
import uuid
import random
import asyncio
from enum import Enum
from typing import List

import sirius_sdk
from sirius_sdk.base import AbstractStateMachine


BAY_DOOR = {
    'server_uri': 'https://demo.socialsirius.com',
    'credentials': 'ez8ucxfrTiV1hPX99MHt/C/MUJCo8OmN4AMVmddE/sew8gBzsOg040FWBSXzHd9hDoj5B5KN4aaLiyzTqkrbD3uaeSwmvxVsqkC0xl5dtIc='.encode(),
    'p2p': sirius_sdk.P2PConnection(
            my_keys=('6QvQ3Y5pPMGNgzvs86N3AQo98pF5WrzM1h6WkKH3dL7f', '28Au6YoU7oPt6YLpbWkzFryhaQbfAcca9KxZEmz22jJaZoKqABc4UJ9vDjNTtmKSn2Axfu8sT52f5Stmt7JD4zzh'),
            their_verkey='Dc85FszkSDcwwYPy8CaveMJqsRvTvZgZ5Q4coaPYpW4k'
        )
}


AIRLOCK_A = {
    'server_uri': 'https://demo.socialsirius.com',
    'credentials': 'ez8ucxfrTiV1hPX99MHt/NRtCY78r2bCZO8nJ7ooWxDa6TQbCWUvnpylTJSRnMq3Doj5B5KN4aaLiyzTqkrbDwMKo4RJ3alpnUUd4iyxgqE='.encode(),
    'p2p': sirius_sdk.P2PConnection(
        my_keys=('5o6wXAYT3A8svdog2t4M3gk15iXNW8yvxVu3utJHAD7g', '2xsAzx4URZGY8imWRL5jFAbQqvdFHw4ZbuxxoAADSqVCFTbiwZYhw4gPVA5dsqbJSsLxbac7ath4sFiHYzyVsEDY'),
        their_verkey='DYL8FLTGYHLisTfYpm6Pk5UwfvT7TPayaW4H1ak7AZTx'
    )
}


AIRLOCK_B = {
    'server_uri': 'https://demo.socialsirius.com',
    'credentials': 'ez8ucxfrTiV1hPX99MHt/P+YgoaBDJV7S03Nxc26pIVlgwkbSZ0XjQ9fEVd4Xrq+Doj5B5KN4aaLiyzTqkrbD8j/KbG7UG4Jfx2kkFcXAvc='.encode(),
    'p2p': sirius_sdk.P2PConnection(
        my_keys=('6RZN88AEYsYQH6WXyunMt8JXLFjenDqrRGeQayG5zY15', '265jVEbBup5EJ9pHJrrRWDnm5rxcZhHkn6FPbcH1su9HMT28yv8BHwithHT8PnFxx91zPVeBiXBvTywqLk3P3vfh'),
        their_verkey='8zkgguAD54sdhc5oF8QKaqSFqmmj4KexZmgJvNECcPno'
    )
}


AIRLOCK_C = {
    'server_uri': 'https://demo.socialsirius.com',
    'credentials': 'ez8ucxfrTiV1hPX99MHt/JZL1h63sUO9saQCgn2BsaC2EndwDSYpOo6eFpn8xP8ZDoj5B5KN4aaLiyzTqkrbDxrbAe/+2uObPTl6xZdXMBs='.encode(),
    'p2p': sirius_sdk.P2PConnection(
        my_keys=('B1n1Hwj1USs7z6FAttHCJcqhg7ARe7xtcyfHJCdXoMnC', 'y7fwmKxfatm6SLN6sqy6LFFjKufgzSsmqA2D4WZz55Y8W7JFeA3LvmicC36E8rdHoAiFhZgSf4fuKmimk9QyBec'),
        their_verkey='aZvq1rY63UZ4t9J1FCPQry7DfgKjzMueSW2DRSPPHPQ'
    )
}


class State(Enum):
    OPENED = 'OPENED'
    CLOSED = 'CLOSED'


class Environment(Enum):
    FRIENDLY = 'FRIENDLY'
    HOSTILE = 'HOSTILE'


class BayDoorStateMachine(AbstractStateMachine):

    def __init__(self, state: State, airlocks: List[sirius_sdk.Pairwise], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = state
        self.airlocks = airlocks

    async def open(self):
        await self.__transition_to(State.OPENED)

    async def close(self):
        await self.__transition_to(State.CLOSED)

    async def __transition_to(self, new_state: State):
        if self.state != new_state:
            random_delay = random.random()
            print(f'Bay Door: start transition from {self.state} to {new_state}')
            await asyncio.sleep(3.0 + random_delay)
            self.state = new_state
            print(f'Bay Door: new state: {self.state}')

    async def __current_environment(self) -> Environment:
        pass
