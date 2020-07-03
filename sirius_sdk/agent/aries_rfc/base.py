from abc import ABC, abstractmethod
from typing import List

from ..coprotocols import AbstractCoProtocolTransport


ARIES_DOC_URI = 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec'


class AbstractStateMachine(ABC):

    def __init__(self, transport: AbstractCoProtocolTransport, time_to_live: int=60):
        self.__transport = transport
        self.__time_to_live = time_to_live

    @property
    def time_to_live(self) -> int:
        return self.__time_to_live

    async def begin(self):
        await self.__transport.start(self.protocols, self.__time_to_live)

    async def end(self):
        await self.__transport.stop()

    @property
    @abstractmethod
    def protocols(self) -> List[str]:
        raise NotImplemented('Need to be implemented in descendant')
