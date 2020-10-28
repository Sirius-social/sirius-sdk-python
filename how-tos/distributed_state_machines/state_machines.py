import json
import uuid
import random
import asyncio
from enum import Enum
from typing import List

import sirius_sdk
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.messaging import Message


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


TYPE_STATE_REQUEST = 'https://didcomm.org/status/1.0/request'
TYPE_STATE_RESPONSE = 'https://didcomm.org/status/1.0/response'


class BayDoorStateMachine(AbstractStateMachine):

    def __init__(self, state: State, airlocks: List[sirius_sdk.Pairwise], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = state
        self.airlocks = airlocks

    async def open(self) -> bool:
        print('Bay Door: start opening')
        environment = await self.__detect_current_environment()
        if environment == Environment.FRIENDLY:
            await self.__transition_to(State.OPENED)
            print('Bay Door: opening finished successfully')
            return True
        else:
            print('Bay Door: opening finished with error due to non Non-Friendly environment')
            return False

    async def close(self):
        await self.__transition_to(State.CLOSED)

    async def __transition_to(self, new_state: State):
        if self.state != new_state:
            random_delay = random.random()
            print(f'Bay Door: start transition from {self.state} to {new_state}')
            await asyncio.sleep(3.0 + random_delay)  # transition operation may take "const +-" delay
            self.state = new_state
            print(f'Bay Door: new state: {self.state}')

    async def __detect_current_environment(self) -> Environment:
        # Open communication channel to transmit requests and await events from participants
        communication = sirius_sdk.CoProtocolThreadedTheirs(
            thid='request-id-' + uuid.uuid4().hex,
            theirs=self.airlocks
        )
        print('Bay Door: check environment')
        # SWITCH method suspend runtime thread until events will be accumulated or error occur
        results = await communication.switch(
            message=Message({
                '@type': TYPE_STATE_REQUEST
            })
        )
        has_error = any([ok is False for airlock, (ok, _) in results])
        if has_error:
            ret = Environment.HOSTILE  # if almost one airlock unreachable environment is hostile
        else:
            # Parse responses
            airlock_statuses = [response['status'] for airlock, (_, response) in results]
            if all([s == State.CLOSED.value for s in airlock_statuses]):
                ret = Environment.FRIENDLY  # All airlocks should be closed
            else:
                ret = Environment.HOSTILE
        print(f'Bay Door: current environment: {ret}')
        return ret


class AirlockStateMachine(AbstractStateMachine):

    def __init__(self, index: int, state: State, baydoor: sirius_sdk.Pairwise, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.index = index
        self.state = state
        self.baydoor = baydoor

    async def open(self) -> bool:
        print(f'AitLock[{self.index}]: start opening')
        environment = await self.__detect_current_environment()
        if environment == Environment.FRIENDLY:
            await self.__transition_to(State.OPENED)
            print(f'AirLock[{self.index}]: opening finished successfully')
            return True
        else:
            print(f'AirLock[{self.index}]: opening finished with error due to non Non-Friendly environment')
            return False

    async def close(self):
        await self.__transition_to(State.CLOSED)

    async def __transition_to(self, new_state: State):
        if self.state != new_state:
            random_delay = random.random()
            print(f'AirLock[{self.index}]: start transition from {self.state} to {new_state}')
            await asyncio.sleep(3.0 + random_delay)  # transition operation may take "const +-" delay
            self.state = new_state
            print(f'AirLock[{self.index}]: new state: {self.state}')

    async def __detect_current_environment(self) -> Environment:
        # Open communication channel to transmit requests and await events from participants
        communication = sirius_sdk.CoProtocolThreadedP2P(
            thid='request-id-' + uuid.uuid4().hex,
            to=self.baydoor
        )
        print(f'AirLock[{self.index}]: check environment')
        # SWITCH method suspend runtime thread until participant will respond or error/timeout occur
        ok, response = await communication.switch(
            message=Message({
                '@type': TYPE_STATE_REQUEST
            })
        )
        if ok:
            if response['status'] == State.CLOSED.value:
                ret = Environment.FRIENDLY  # Bay door should be closed for Friendly environment
            else:
                ret = Environment.HOSTILE
        else:
            # Timeout occur
            ret = Environment.HOSTILE
        print(f'AitLock[{self.index}]: current environment: {ret}')
        return ret


class BayDoor:

    def __init__(self, state: State, airlocks: List[sirius_sdk.Pairwise]):
        self.state_machine = BayDoorStateMachine(state, airlocks)

        async def reactive_nature():
            async with sirius_sdk.context(**BAY_DOOR):
                listener = await sirius_sdk.subscribe()
                async for event in listener:
                    if event.message['@type'] == TYPE_STATE_REQUEST and event.pairwise is not None:
                        cur_state = self.state_machine.state.value
                        communication
