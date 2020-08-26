from typing import List, Optional

from sirius_sdk.agent.wallet import RetrieveRecordOptions
from sirius_sdk.agent.wallet.abstract.non_secrets import AbstractNonSecrets
from sirius_sdk.agent.connections import AgentRPC


class NonSecretsProxy(AbstractNonSecrets):

    def __init__(self, rpc: AgentRPC):
        self.__rpc = rpc

    async def add_wallet_record(self, type_: str, id_: str, value: str, tags: dict = None) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/add_wallet_record',
            params=dict(type_=type_, id_=id_, value=value, tags=tags)
        )

    async def update_wallet_record_value(self, type_: str, id_: str, value: str) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/update_wallet_record_value',
            params=dict(type_=type_, id_=id_, value=value)
        )

    async def update_wallet_record_tags(self, type_: str, id_: str, tags: dict) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/update_wallet_record_tags',
            params=dict(type_=type_, id_=id_, tags=tags)
        )

    async def add_wallet_record_tags(self, type_: str, id_: str, tags: dict) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/add_wallet_record_tags',
            params=dict(type_=type_, id_=id_, tags=tags)
        )

    async def delete_wallet_record_tags(self, type_: str, id_: str, tag_names: List[str]) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/delete_wallet_record_tags',
            params=dict(type_=type_, id_=id_, tag_names=tag_names)
        )

    async def delete_wallet_record(self, type_: str, id_: str) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/delete_wallet_record',
            params=dict(type_=type_, id_=id_)
        )

    async def get_wallet_record(self, type_: str, id_: str, options: RetrieveRecordOptions) -> Optional[dict]:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/get_wallet_record',
            params=dict(type_=type_, id_=id_, options=options)
        )

    async def wallet_search(
            self, type_: str, query: dict, options: RetrieveRecordOptions, limit: int = 1
    ) -> (List[dict], int):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/wallet_search',
            params=dict(type_=type_, query=query, options=options, limit=limit)
        )
