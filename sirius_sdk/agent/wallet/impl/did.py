from typing import Any, Optional, List

from sirius_sdk.agent.connections import AgentRPC
from sirius_sdk.agent.wallet.abstract.did import AbstractDID


class DIDProxy(AbstractDID):

    def __init__(self, rpc: AgentRPC):
        self.__rpc = rpc

    async def create_and_store_my_did(self, did: str = None, seed: str = None, cid: bool = None) -> (str, str):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/create_and_store_my_did',
            params=dict(did=did, seed=seed, cid=cid)
        )

    async def store_their_did(self, did: str, verkey: str = None) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/store_their_did',
            params=dict(did=did, verkey=verkey)
        )

    async def set_did_metadata(self, did: str, metadata: dict = None) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/set_did_metadata',
            params=dict(did=did, metadata=metadata)
        )

    async def list_my_dids_with_meta(self) -> List[Any]:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/list_my_dids_with_meta'
        )

    async def get_did_metadata(self, did) -> Optional[dict]:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/get_did_metadata',
            params=dict(did=did)
        )

    async def key_for_local_did(self, did: str) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/key_for_local_did',
            params=dict(did=did)
        )

    async def key_for_did(self, pool_name: str, did: str) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/key_for_did',
            params=dict(pool_name=pool_name, did=did)
        )

    async def create_key(self, seed: str = None) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/create_key__did',
            params=dict(seed=seed)
        )

    async def replace_keys_start(self, did: str, seed: str = None) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/replace_keys_start',
            params=dict(did=did, seed=seed)
        )

    async def replace_keys_apply(self, did: str) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/replace_keys_apply',
            params=dict(did=did)
        )

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/set_key_metadata__did',
            params=dict(verkey=verkey, metadata=metadata)
        )

    async def get_key_metadata(self, verkey: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/get_key_metadata__did',
            params=dict(verkey=verkey)
        )

    async def set_endpoint_for_did(self, did: str, address: str, transport_key: str) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/set_endpoint_for_did',
            params=dict(did=did, address=address, transport_key=transport_key)
        )

    async def get_endpoint_for_did(self, pool_name: str, did: str) -> (str, Optional[str]):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/get_endpoint_for_did',
            params=dict(pool_name=pool_name, did=did)
        )

    async def get_my_did_with_meta(self, did: str) -> Any:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/get_my_did_with_meta',
            params=dict(did=did)
        )

    async def abbreviate_verkey(self, did: str, full_verkey: str) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/abbreviate_verkey',
            params=dict(did=did, full_verkey=full_verkey)
        )

    async def qualify_did(self, did: str, method: str) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/qualify_did',
            params=dict(did=did, method=method)
        )
