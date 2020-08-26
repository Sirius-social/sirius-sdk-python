from typing import Optional, List, Any

from sirius_sdk.agent.wallet.abstract.pairwise import AbstractPairwise
from sirius_sdk.agent.connections import AgentRPC


class PairwiseProxy(AbstractPairwise):

    def __init__(self, rpc: AgentRPC):
        self.__rpc = rpc

    async def is_pairwise_exists(self, their_did: str) -> bool:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/is_pairwise_exists',
            params=dict(their_did=their_did)
        )

    async def create_pairwise(self, their_did: str, my_did: str, metadata: dict = None, tags: dict = None) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/create_pairwise',
            params=dict(their_did=their_did, my_did=my_did, metadata=metadata, tags=tags)
        )

    async def list_pairwise(self) -> List[Any]:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/list_pairwise'
        )

    async def get_pairwise(self, their_did: str) -> Optional[dict]:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/get_pairwise',
            params=dict(their_did=their_did)
        )

    async def set_pairwise_metadata(self, their_did: str, metadata: dict = None, tags: dict = None) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/set_pairwise_metadata',
            params=dict(their_did=their_did, metadata=metadata, tags=tags)
        )

    async def search(self, tags: dict, limit: int = None) -> (List[dict], int):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/search_pairwise',
            params=dict(tags=tags, limit=limit)
        )
