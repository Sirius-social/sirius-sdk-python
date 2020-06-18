import asyncio

from sirius_sdk.base import ReadOnlyChannel, WriteOnlyChannel
from sirius_sdk.errors.exceptions import SiriusTimeoutIO


class InMemoryChannel(ReadOnlyChannel, WriteOnlyChannel):

    def __init__(self):
        self.queue = asyncio.Queue()

    async def read(self, timeout: int = None) -> bytes:

        ret = None

        async def internal_reading():
            nonlocal ret
            ret = await self.queue.get()
            print('!')

        done, pending = await asyncio.wait([internal_reading()], timeout=timeout)

        for coro in pending:
            coro.cancel()
        if isinstance(ret, bytes):
            return ret
        else:
            raise SiriusTimeoutIO()

    async def write(self, data: bytes) -> bool:
        await self.queue.put(data)
        return True
