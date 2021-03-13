from abc import ABC, abstractmethod
from typing import List

from sirius_sdk.agent.connections import AgentRPC


class AbstractLocks(ABC):

    @abstractmethod
    async def acquire(self, resources: List[str], lock_timeout: float, enter_timeout: float = None) -> (bool, List[str]):
        pass

    @abstractmethod
    async def release(self):
        pass


class Locks(AbstractLocks):

    def __init__(self, rpc: AgentRPC):
        self.__rpc = rpc

    async def acquire(self, resources: List[str], lock_timeout: float, enter_timeout: float = None) -> (bool, List[str]):
        success, busy = await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/admin/1.0/acquire',
            params={
                'names': resources,
                'enter_timeout': enter_timeout,
                'lock_timeout': lock_timeout
            }
        )
        return success, busy

    async def release(self):
        await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/admin/1.0/release'
        )
