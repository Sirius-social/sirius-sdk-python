import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Any
from contextlib import asynccontextmanager

from sirius_sdk.agent.pairwise import Pairwise, TheirEndpoint
from sirius_sdk.messaging import Message
from sirius_sdk.agent.coprotocols import TheirEndpointCoProtocolTransport, PairwiseCoProtocolTransport

from .core import _current_hub, init, context


class AbstractCoProtocol(ABC):

    def __init__(self, time_to_live: int = None):
        self.__time_to_live = time_to_live
        self.__is_start = False

    @property
    def time_to_live(self) -> Optional[int]:
        return self.__time_to_live

    @abstractmethod
    async def send(self, message: Message):
        pass

    @abstractmethod
    async def switch(self, message: Message) -> (bool, Message):
        pass


class CoProtocolAnon(AbstractCoProtocol):

    def __init__(self, my_verkey: str, endpoint: TheirEndpoint, time_to_live: int = None):
        super().__init__(time_to_live=time_to_live)
        self.__is_start = False
        self.__transport = None
        self.__my_verkey = my_verkey
        self.__endpoint = endpoint

    def __del__(self):
        if self.__is_start:
            asyncio.ensure_future(self.__transport.stop())

    async def send(self, message: Message):
        async with self.__get_transport_lazy() as transport:
            await transport.send(message)

    async def switch(self, message: Message) -> (bool, Message):
        async with self.__get_transport_lazy() as transport:
            success, response = await transport.switch(message)
        return success, response

    @asynccontextmanager
    async def __get_transport_lazy(self) -> TheirEndpointCoProtocolTransport:
        if self.__transport is None:
            async with _current_hub().get_agent_connection_lazy() as agent:
                self.__transport = await agent.spawn(self.__my_verkey, self.__endpoint)
                await self.__transport.start(protocols=[], time_to_live=self.time_to_live)
                self.__is_start = True
        return self.__transport


class CoProtocolP2P(AbstractCoProtocol):

    def __init__(self, pairwise: Pairwise, time_to_live: int = None):
        super().__init__(time_to_live=time_to_live)
        self.__is_start = False
        self.__transport = None
        self.__pairwise = pairwise

    def __del__(self):
        if self.__is_start:
            asyncio.ensure_future(self.__transport.stop())

    async def send(self, message: Message):
        async with self.__get_transport_lazy() as transport:
            await transport.send(message)

    async def switch(self, message: Message) -> (bool, Message):
        async with self.__get_transport_lazy() as transport:
            success, response = await transport.switch(message)
        return success, response

    @asynccontextmanager
    async def __get_transport_lazy(self) -> PairwiseCoProtocolTransport:
        if self.__transport is None:
            async with _current_hub().get_agent_connection_lazy() as agent:
                self.__transport = await agent.spawn(self.__pairwise)
                await self.__transport.start(protocols=[], time_to_live=self.time_to_live)
                self.__is_start = True
        return self.__transport


class CoProtocolThreaded(AbstractCoProtocol):

    def __init__(self, thid: str, to: List[Pairwise], pthid: str = None, time_to_live: int = None):
        super().__init__(time_to_live=time_to_live)
        self.__is_start = False
        self.__thid = thid
        self.__pthid = pthid
        self.__transport = None
        self.__to = to

    def __del__(self):
        if self.__is_start:
            asyncio.ensure_future(self.__transport.stop())

    async def send(self, message: Message) -> List[Any]:
        async with self.__get_transport_lazy() as transport:
            ret = await transport.send_many(message, self.__to)
        return ret

    async def switch(self, message: Message) -> (bool, Message):
        pass

    @asynccontextmanager
    async def __get_transport_lazy(self) -> TheirEndpointCoProtocolTransport:
        if self.__transport is None:
            async with _current_hub().get_agent_connection_lazy() as agent:
                if self.__pthid is None:
                    self.__transport = await agent.spawn(self.__thid)
                else:
                    self.__transport = await agent.spawn(self.__thid, self.__pthid)
                await self.__transport.start(protocols=[], time_to_live=self.time_to_live)
                self.__is_start = True
        return self.__transport
