import asyncio
import functools
from typing import Optional

import sirius_sdk


def hash_dict(func):
    """Transform mutable dictionnary
    Into immutable
    Useful to be compatible with cache
    """

    class HDict(dict):
        def __hash__(self):
            return hash(frozenset(self.items()))

    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        args = tuple([HDict(arg) if isinstance(arg, dict) else arg for arg in args])
        kwargs = {k: HDict(v) if isinstance(v, dict) else v for k, v in kwargs.items()}
        return func(*args, **kwargs)
    return wrapped


@hash_dict
@functools.lru_cache()
def establish_connection(my_context: dict, my_did: str, their_context: dict, their_did: str) -> sirius_sdk.Pairwise:

    pairwise: Optional[sirius_sdk.Pairwise] = None

    async def runner():
        nonlocal pairwise
        # Theirs
        async with sirius_sdk.context(**their_context):
            metadata = await sirius_sdk.DID.get_my_did_with_meta(their_did)
            endpoints = await sirius_sdk.endpoints()
            their_endpoint = [e for e in endpoints if e.routing_keys == []][0]
            their = sirius_sdk.Pairwise.Their(
                their_did, 'Their', their_endpoint.address, metadata['verkey']
            )
        # Mine
        async with sirius_sdk.context(**my_context):
            already_exists = await sirius_sdk.PairwiseList.is_exists(their_did)
            metadata = await sirius_sdk.DID.get_my_did_with_meta(my_did)
            if already_exists:
                pairwise = await sirius_sdk.PairwiseList.load_for_did(their_did)
            else:
                pairwise = sirius_sdk.Pairwise(
                    me=sirius_sdk.Pairwise.Me(my_did, metadata['verkey']),
                    their=their
                )
                await sirius_sdk.PairwiseList.create(pairwise)

    asyncio.get_event_loop().run_until_complete(runner())
    return pairwise
