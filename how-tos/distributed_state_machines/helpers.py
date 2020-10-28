import asyncio
from enum import Enum
from abc import abstractmethod
from typing import Optional

import sirius_sdk


class State(Enum):
    OPENED = 'OPENED'
    CLOSED = 'CLOSED'


def establish_connection(my_context: dict, my_seed: str, their_context: dict, their_seed: str) -> sirius_sdk.Pairwise:

    pairwise: Optional[sirius_sdk.Pairwise] = None

    async def runner():
        nonlocal pairwise
        # Theirs
        async with sirius_sdk.context(**their_context):
            did, verkey = await sirius_sdk.DID.create_and_store_my_did(seed=their_seed)
            endpoints = await sirius_sdk.endpoints()
            simple_endpoint = [e for e in endpoints if e.routing_keys == []][0]
            their = sirius_sdk.Pairwise.Their(did, 'Label', simple_endpoint.address, verkey)
        # Mine
        async with sirius_sdk.context(**my_context):
            already_exists = await sirius_sdk.PairwiseList.is_exists(their.did)
            if already_exists:
                pairwise = await sirius_sdk.PairwiseList.load_for_did(their.did)
            else:
                did, verkey = await sirius_sdk.DID.create_and_store_my_did(seed=my_seed)
                pairwise = sirius_sdk.Pairwise(
                    me=sirius_sdk.Pairwise.Me(did, verkey),
                    their=their
                )
                await sirius_sdk.PairwiseList.create(pairwise)

    asyncio.get_event_loop().run_until_complete(runner())
    return pairwise


class AbstractDevice:

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplemented

    @abstractmethod
    async def open(self) -> bool:
        raise NotImplemented

    @abstractmethod
    async def close(self) -> bool:
        raise NotImplemented

    @property
    @abstractmethod
    def state(self) -> State:
        raise NotImplemented
