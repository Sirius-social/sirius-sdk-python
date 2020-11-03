import os
import sys
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
from helpers import establish_connection, AbstractDevice, State


BAY_DOOR = AGENT1
AIRLOCK_A = AGENT2
AIRLOCK_B = AGENT3
AIRLOCK_C = AGENT4
# Seeds to ensure public DIDs are persistent
BAYDOOR_SEED = '00000000000000000000000xxBAYDOOR'
AIRLOCK_A_SEED = '0000000000000000000000xxAIRLOCKA'
AIRLOCK_B_SEED = '0000000000000000000000xxAIRLOCKB'
AIRLOCK_C_SEED = '0000000000000000000000xxAIRLOCKC'


class Environment(Enum):
    FRIENDLY = 'FRIENDLY'
    HOSTILE = 'HOSTILE'


TYPE_STATE_REQUEST = 'https://didcomm.org/status/1.0/request'
TYPE_STATE_RESPONSE = 'https://didcomm.org/status/1.0/response'


def log(message: str):
    print(f'\t\t{message}')


class BayDoor(AbstractStateMachine, AbstractDevice):

    def __init__(self, state: State, airlocks: List[sirius_sdk.Pairwise], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state = state
        self.airlocks = airlocks

    @property
    def name(self) -> str:
        return 'Bay Door'

    @property
    def state(self) -> State:
        return self._state

    async def open(self) -> bool:
        log('Bay Door: start opening')
        # Detect if Environment is Friendly or No to make decision
        environment = await self.__detect_current_environment()
        if environment == Environment.FRIENDLY:
            await self.__transition_to(State.OPENED)
            log('Bay Door: opening finished successfully')
            return True
        else:
            log('Bay Door: opening finished with error due to non Non-Friendly environment')
            return False

    async def close(self) -> bool:
        await self.__transition_to(State.CLOSED)
        return True

    async def listen(self):
        # Bay door may acts as reactor: respond other devices with self status, etc. according to events protocol
        # So, Sirius SDK provide building blocks to implement reactive nature of the Entity
        async with sirius_sdk.context(**BAY_DOOR):
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                if event.message['@type'] == TYPE_STATE_REQUEST and event.pairwise is not None:
                    # Open communication channel from income event context
                    communication = await sirius_sdk.open_communication(event)
                    await communication.send(
                        message=Message({
                            '@type': TYPE_STATE_RESPONSE,
                            'status': self.state.value
                        })
                    )

    async def __transition_to(self, new_state: State):
        if self.state != new_state:
            random_delay = random.random()
            log(f'Bay Door: start transition from {self.state} to {new_state}')
            await asyncio.sleep(3.0 + random_delay)  # transition operation may take "const +-" delay
            self._state = new_state
            log(f'Bay Door: new state: {self.state}')
        else:
            log(f'Bay Door: nothing to do. State not changed')

    async def __detect_current_environment(self) -> Environment:
        async with sirius_sdk.context(**BAY_DOOR):
            # Open communication channel to transmit requests and await events from participants
            communication = sirius_sdk.CoProtocolThreadedTheirs(
                thid='request-id-' + uuid.uuid4().hex,
                theirs=self.airlocks,
                time_to_live=5
            )
            log('Bay Door: check environment')
            # SWITCH method suspend runtime thread until events will be accumulated or error occur
            results = await communication.switch(
                message=Message({
                    '@type': TYPE_STATE_REQUEST
                })
            )
            has_error = any([ok is False for airlock, (ok, _) in results.items()])
            if has_error:
                ret = Environment.HOSTILE  # if almost one airlock unreachable environment is hostile
            else:
                # Parse responses
                airlock_statuses = [response['status'] for airlock, (_, response) in results.items()]
                if all([s == State.CLOSED.value for s in airlock_statuses]):
                    ret = Environment.FRIENDLY  # All airlocks should be closed
                else:
                    ret = Environment.HOSTILE
            log(f'Bay Door: current environment: {ret}')
            return ret


class Airlock(AbstractStateMachine, AbstractDevice):

    def __init__(self, index: str, state: State, baydoor: sirius_sdk.Pairwise, hub_credentials: dict, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.index = index
        self._state = state
        self.baydoor = baydoor
        self.hub_credentials = hub_credentials

    @property
    def name(self) -> str:
        return f'AirLock {self.index}'

    @property
    def state(self) -> State:
        return self._state

    async def open(self) -> bool:
        log(f'AitLock[{self.index}]: start opening')
        environment = await self.__detect_current_environment()
        if environment == Environment.FRIENDLY:
            await self.__transition_to(State.OPENED)
            log(f'AirLock[{self.index}]: opening finished successfully')
            return True
        else:
            log(f'AirLock[{self.index}]: opening finished with error due to non Non-Friendly environment')
            return False

    async def close(self) -> bool:
        await self.__transition_to(State.CLOSED)
        return True

    async def listen(self):
        log(f'{self.name} listener started')
        # AirLock acts as reactor: respond other devices with self status, etc. according to events protocol
        # So, Sirius SDK provide building blocks to implement reactive nature of the Entity
        async with sirius_sdk.context(**self.hub_credentials):
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                if event.message['@type'] == TYPE_STATE_REQUEST and event.pairwise is not None:
                    log(f'{self.name}: \tprocess state request')
                    # Open communication channel from income event context
                    communication = await sirius_sdk.open_communication(event)
                    await communication.send(
                        message=Message({
                            '@type': TYPE_STATE_RESPONSE,
                            'status': self.state.value
                        })
                    )

    async def __transition_to(self, new_state: State):
        if self.state != new_state:
            random_delay = random.random()
            log(f'AirLock[{self.index}]: start transition from {self.state} to {new_state}')
            await asyncio.sleep(1.0 + random_delay)  # transition operation may take "const +-" delay
            self._state = new_state
            log(f'AirLock[{self.index}]: new state: {self.state}')
        else:
            log(f'AirLock[{self.index}]: nothing to do. State not changed')

    async def __detect_current_environment(self) -> Environment:
        async with sirius_sdk.context(**self.hub_credentials):
            # Open communication channel to transmit requests and await events from participants
            communication = sirius_sdk.CoProtocolThreadedP2P(
                thid='request-id-' + uuid.uuid4().hex,
                to=self.baydoor,
                time_to_live=5
            )
            log(f'AirLock[{self.index}]: check environment')
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
            log(f'AitLock[{self.index}]: current environment: {ret}')
            return ret


if __name__ == '__main__':

    # Initialize Bay Door
    bay_door = BayDoor(
        state=State.CLOSED,
        airlocks=[
            establish_connection(BAY_DOOR, BAYDOOR_SEED, AIRLOCK_A, AIRLOCK_A_SEED),
            establish_connection(BAY_DOOR, BAYDOOR_SEED, AIRLOCK_B, AIRLOCK_B_SEED),
            establish_connection(BAY_DOOR, BAYDOOR_SEED, AIRLOCK_C, AIRLOCK_C_SEED)
        ]
    )

    # Initialize AirLocks
    airlockA = Airlock(
        index='A', state=State.CLOSED,
        baydoor=establish_connection(AIRLOCK_A, AIRLOCK_A_SEED, BAY_DOOR, BAYDOOR_SEED),
        hub_credentials=AIRLOCK_A
    )
    airlockB = Airlock(
        index='B', state=State.CLOSED,
        baydoor=establish_connection(AIRLOCK_B, AIRLOCK_B_SEED, BAY_DOOR, BAYDOOR_SEED),
        hub_credentials=AIRLOCK_B
    )
    airlockC = Airlock(
        index='C', state=State.CLOSED,
        baydoor=establish_connection(AIRLOCK_C, AIRLOCK_C_SEED, BAY_DOOR, BAYDOOR_SEED),
        hub_credentials=AIRLOCK_C
    )
    print('')

    def print_states():
        print('Devices states:')
        print(f'\t[1] Bay Door:  \t{bay_door.state}')
        print(f'\t[2] AirLock A: \t{airlockA.state}')
        print(f'\t[3] AirLock B: \t{airlockB.state}')
        print(f'\t[4] AirLock C: \t{airlockC.state}')

    async def process_device(device: AbstractDevice):
        print(f'\tYou entered device: {device.name} with state: {device.state}')
        case = input('\tSelect operation (open, close): ')
        if case == 'open':
            await device.open()
        elif case == 'close':
            await device.close()
        else:
            print('\t!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
            print('\tYou entered unexpected case...')
            print('\t!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')

    async def run():
        await asyncio.sleep(1)
        while True:
            print_states()
            case = input('Select device (1, 2, 3, 4, exit): ')
            await asyncio.sleep(1)
            device = None
            if case == '1':
                device = bay_door
            elif case == '2':
                device = airlockA
            elif case == '3':
                device = airlockB
            elif case == '4':
                device = airlockC
            elif case == 'exit':
                exit(0)
            else:
                print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
                print('You entered unexpected case...')
                print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
            if device:
                await process_device(device)

    # Schedule devices listeners. Device should react to state requests
    asyncio.ensure_future(bay_door.listen())
    asyncio.ensure_future(airlockA.listen())
    asyncio.ensure_future(airlockB.listen())
    asyncio.ensure_future(airlockC.listen())
    asyncio.get_event_loop().run_until_complete(run())
