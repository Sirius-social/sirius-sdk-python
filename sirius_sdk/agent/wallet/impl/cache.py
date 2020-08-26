from sirius_sdk.agent.connections import AgentRPC
from sirius_sdk.agent.wallet.abstract.cache import AbstractCache, PurgeOptions, CacheOptions


class CacheProxy(AbstractCache):

    def __init__(self, rpc: AgentRPC):
        self.__rpc = rpc

    async def get_schema(self, pool_name: str, submitter_did: str, id_: str, options: CacheOptions) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/get_schema',
            params=dict(pool_name=pool_name, submitter_did=submitter_did, id_=id_, options=options)
        )

    async def get_cred_def(self, pool_name: str, submitter_did: str, id_: str, options: CacheOptions) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/get_cred_def',
            params=dict(pool_name=pool_name, submitter_did=submitter_did, id_=id_, options=options)
        )

    async def purge_schema_cache(self, options: PurgeOptions) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/purge_schema_cache',
            params=dict(options=options)
        )

    async def purge_cred_def_cache(self, options: PurgeOptions) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/purge_cred_def_cache',
            params=dict(options=options)
        )
