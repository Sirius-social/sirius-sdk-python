import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Any
from contextlib import asynccontextmanager

from sirius_sdk.agent.pairwise import Pairwise, TheirEndpoint
from sirius_sdk.messaging import Message
from sirius_sdk.errors.exceptions import SiriusContextError

from .core import _current_hub


PLEASE_ACK_DECORATOR = '~please_ack'
THREAD_DECORATOR = '~thread'


class AbstractCoProtocol(ABC):

    def __init__(self, protocols: List[str], time_to_live: int = None):
        self.__time_to_live = time_to_live
        if not protocols:
            raise SiriusContextError('You must set protocols list. It is empty for now!')
        self.__protocols = protocols

    @property
    def protocols(self) -> List[str]:
        return self.__protocols

    @property
    def time_to_live(self) -> Optional[int]:
        return self.__time_to_live

    @abstractmethod
    async def send(self, message: Message):
        pass

    @abstractmethod
    async def switch(self, message: Message) -> (bool, Message):
        pass

    @abstractmethod
    async def done(self):
        pass


class CoProtocolAnon(AbstractCoProtocol):

    def __init__(self, my_verkey: str, endpoint: TheirEndpoint, protocols: List[str], time_to_live: int = None):
        super().__init__(protocols=protocols, time_to_live=time_to_live)
        self.__is_start = False
        self.__transport = None
        self.__my_verkey = my_verkey
        self.__endpoint = endpoint
        self.__thread_id = None

    def __del__(self):
        if self.__is_start:
            asyncio.ensure_future(self.__transport.stop())

    async def send(self, message: Message):
        async with self.__get_transport_lazy() as transport:
            self.__setup(message, please_ack=False)
            await transport.send(message)

    async def switch(self, message: Message) -> (bool, Message):
        async with self.__get_transport_lazy() as transport:
            self.__setup(message)
            success, response = await transport.switch(message)
            if success:
                if PLEASE_ACK_DECORATOR in response:
                    self.__thread_id = response.get(PLEASE_ACK_DECORATOR, {}).get('message_id', None) or message.id
                else:
                    self.__thread_id = None
        return success, response

    async def done(self):
        if self.__is_start:
            await self.__transport.stop()
            self.__is_start = False

    def __setup(self, message: Message, please_ack: bool = True):
        if please_ack:
            if PLEASE_ACK_DECORATOR not in message:
                message[PLEASE_ACK_DECORATOR] = {'message_id': message.id}
        if self.__thread_id:
            thread = message.get(THREAD_DECORATOR, {})
            if 'thid' not in thread:
                thread['thid'] = self.__thread_id
                message[THREAD_DECORATOR] = thread

    @asynccontextmanager
    async def __get_transport_lazy(self):
        if self.__transport is None:
            async with _current_hub().get_agent_connection_lazy() as agent:
                self.__transport = await agent.spawn(self.__my_verkey, self.__endpoint)
                await self.__transport.start(protocols=self.protocols, time_to_live=self.time_to_live)
                self.__is_start = True
        yield self.__transport


class CoProtocolP2P(AbstractCoProtocol):

    def __init__(self, pairwise: Pairwise, protocols: List[str], time_to_live: int = None):
        super().__init__(protocols=protocols, time_to_live=time_to_live)
        self.__is_start = False
        self.__transport = None
        self.__pairwise = pairwise
        self.__thread_id = None

    def __del__(self):
        if self.__is_start:
            asyncio.ensure_future(self.__transport.stop())

    async def send(self, message: Message):
        async with self.__get_transport_lazy() as transport:
            self.__setup(message, please_ack=False)
            await transport.send(message)

    async def switch(self, message: Message) -> (bool, Message):
        async with self.__get_transport_lazy() as transport:
            self.__setup(message)
            success, response = await transport.switch(message)
            if PLEASE_ACK_DECORATOR in response:
                self.__thread_id = response.get(PLEASE_ACK_DECORATOR, {}).get('message_id', None) or message.id
            else:
                self.__thread_id = None
        return success, response

    async def done(self):
        if self.__is_start:
            await self.__transport.stop()
            self.__is_start = False

    def __setup(self, message: Message, please_ack: bool = True):
        if please_ack:
            if PLEASE_ACK_DECORATOR not in message:
                message[PLEASE_ACK_DECORATOR] = {'message_id': message.id}
        if self.__thread_id:
            thread = message.get(THREAD_DECORATOR, {})
            if 'thid' not in thread:
                thread['thid'] = self.__thread_id
                message[THREAD_DECORATOR] = thread

    @asynccontextmanager
    async def __get_transport_lazy(self):
        if self.__transport is None:
            async with _current_hub().get_agent_connection_lazy() as agent:
                self.__transport = await agent.spawn(self.__pairwise)
                await self.__transport.start(protocols=self.protocols, time_to_live=self.time_to_live)
                self.__is_start = True
        yield self.__transport


class CoProtocolThreaded(AbstractCoProtocol):

    def __init__(self, thid: str, to: List[Pairwise], protocols: List[str], pthid: str = None, time_to_live: int = None):
        super().__init__(protocols=protocols, time_to_live=time_to_live)
        self.__is_start = False
        self.__thid = thid
        self.__pthid = pthid
        self.__to = to
        self.__sender_order = 0
        self.__received_orders = {}
        self.__transport = None

    def __del__(self):
        if self.__is_start:
            asyncio.ensure_future(self.__transport.stop())

    async def send(self, message: Message) -> List[Any]:
        async with self.__get_transport_lazy() as transport:
            self.__prepare_message(message)
            ret = await transport.send_many(message, self.__to)
        return ret

    async def switch(self, message: Message) -> (bool, List[Message]):
        self.__prepare_message(message)

    async def done(self):
        if self.__is_start:
            await self.__transport.stop()
            self.__is_start = False

    def __prepare_message(self, message: Message):
        if THREAD_DECORATOR not in message:  # Don't rewrite existing ~thread decorator
            thread_decorator = {
                'thid': self.__thid,
                'sender_order': self.__sender_order
            }
            if self.__pthid:
                thread_decorator['pthid'] = self.__pthid
            if self.__received_orders:
                thread_decorator['received_orders'] = self.__received_orders
            self.__sender_order += 1
            message[THREAD_DECORATOR] = thread_decorator

    @asynccontextmanager
    async def __get_transport_lazy(self):
        if self.__transport is None:
            async with _current_hub().get_agent_connection_lazy() as agent:
                if self.__pthid is None:
                    self.__transport = await agent.spawn(self.__thid)
                else:
                    self.__transport = await agent.spawn(self.__thid, self.__pthid)
                await self.__transport.start(protocols=self.protocols, time_to_live=self.time_to_live)
                self.__is_start = True
        yield self.__transport
