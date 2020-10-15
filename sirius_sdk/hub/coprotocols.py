import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Any, Union
from contextlib import asynccontextmanager

from sirius_sdk.agent.pairwise import Pairwise, TheirEndpoint
from sirius_sdk.messaging import Message
from sirius_sdk.errors.exceptions import SiriusContextError, OperationAbortedManually, SiriusConnectionClosed

from .core import _current_hub


PLEASE_ACK_DECORATOR = '~please_ack'
THREAD_DECORATOR = '~thread'


class AbstractCoProtocol(ABC):

    def __init__(self, time_to_live: int = None):
        self.__time_to_live = time_to_live
        self.__is_aborted = False
        self._agent = None

    @property
    def is_aborted(self) -> bool:
        return self.__is_aborted

    @property
    def time_to_live(self) -> Optional[int]:
        return self.__time_to_live

    @abstractmethod
    async def send(self, message: Message):
        pass

    @abstractmethod
    async def get_one(self) -> (Optional[Message], str, Optional[str]):
        """
        return message, sender_verkey, recipient_verkey
        """
        pass

    @abstractmethod
    async def switch(self, message: Message) -> (bool, Message):
        pass

    @abstractmethod
    async def abort(self):
        if not self.__is_aborted:
            self.__is_aborted = True
            if self._agent:
                await self._agent.abort()
                self._agent = None


class CoProtocolAnon(AbstractCoProtocol):

    def __init__(self, my_verkey: str, endpoint: TheirEndpoint, protocols: List[str], time_to_live: int = None):
        if not protocols:
            raise SiriusContextError('You must set protocols list. It is empty for now!')
        super().__init__(time_to_live=time_to_live)
        self.__is_start = False
        self.__transport = None
        self.__my_verkey = my_verkey
        self.__endpoint = endpoint
        self.__thread_id = None
        self.__protocols = protocols

    def __del__(self):
        if self.__is_start and asyncio.get_event_loop().is_running():
            asyncio.ensure_future(self.__transport.stop())

    @property
    def protocols(self) -> List[str]:
        return self.__protocols

    async def send(self, message: Message):
        async with self.__get_transport_lazy() as transport:
            self.__setup(message, please_ack=False)
            await transport.send(message)

    async def get_one(self) -> (Optional[Message], str, Optional[str]):
        """
        return message, sender_verkey, recipient_verkey
        """
        async with self.__get_transport_lazy() as transport:
            message, sender_verkey, recipient_verkey = await transport.get_one()
        return message, sender_verkey, recipient_verkey

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

    async def abort(self):
        if self.__is_start:
            await self.__transport.stop()
            self.__is_start = False
        self.__transport = None
        await super().abort()

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
                self._agent = agent
                await self.__transport.start(protocols=self.protocols, time_to_live=self.time_to_live)
                self.__is_start = True
        try:
            yield self.__transport
        except SiriusConnectionClosed:
            if self.is_aborted:
                raise OperationAbortedManually('User aborted operation')
            else:
                raise


class CoProtocolP2P(AbstractCoProtocol):

    def __init__(self, pairwise: Pairwise, protocols: List[str], time_to_live: int = None):
        if not protocols:
            raise SiriusContextError('You must set protocols list. It is empty for now!')
        super().__init__(time_to_live=time_to_live)
        self.__is_start = False
        self.__transport = None
        self.__pairwise = pairwise
        self.__thread_id = None
        self.__protocols = protocols

    def __del__(self):
        if self.__is_start and asyncio.get_event_loop().is_running():
            asyncio.ensure_future(self.__transport.stop())

    @property
    def protocols(self) -> List[str]:
        return self.__protocols

    async def send(self, message: Message):
        async with self.__get_transport_lazy() as transport:
            self.__setup(message, please_ack=False)
            await transport.send(message)

    async def get_one(self) -> (Optional[Message], str, Optional[str]):
        """
        return message, sender_verkey, recipient_verkey
        """
        async with self.__get_transport_lazy() as transport:
            message, sender_verkey, recipient_verkey = await transport.get_one()
        return message, sender_verkey, recipient_verkey

    async def switch(self, message: Message) -> (bool, Message):
        async with self.__get_transport_lazy() as transport:
            self.__setup(message)
            success, response = await transport.switch(message)
            if PLEASE_ACK_DECORATOR in response:
                self.__thread_id = response.get(PLEASE_ACK_DECORATOR, {}).get('message_id', None) or message.id
            else:
                self.__thread_id = None
        return success, response

    async def abort(self):
        if self.__is_start:
            await self.__transport.stop()
            self.__is_start = False
        self.__transport = None
        await super().abort()

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
                self._agent = agent
                await self.__transport.start(protocols=self.protocols, time_to_live=self.time_to_live)
                self.__is_start = True
        try:
            yield self.__transport
        except SiriusConnectionClosed:
            if self.is_aborted:
                raise OperationAbortedManually('User aborted operation')
            else:
                raise


class CoProtocolThreaded(AbstractCoProtocol):

    def __init__(self, thid: str, to: Pairwise, pthid: str = None, time_to_live: int = None):
        super().__init__(time_to_live=time_to_live)
        self.__is_start = False
        self.__thid = thid
        self.__pthid = pthid
        self.__to = to
        self.__sender_order = 0
        self.__received_orders = {}
        self.__transport = None

    def __del__(self):
        if self.__is_start and asyncio.get_event_loop().is_running():
            asyncio.ensure_future(self.__transport.stop())

    @property
    def thid(self) -> str:
        return self.__thid

    @property
    def pthid(self) -> Optional[str]:
        return self.__pthid

    async def send(self, message: Message):
        async with self.__get_transport_lazy() as transport:
            await transport.send(message)

    async def get_one(self) -> (Optional[Message], str, Optional[str]):
        """
        return message, sender_verkey, recipient_verkey
        """
        async with self.__get_transport_lazy() as transport:
            message, sender_verkey, recipient_verkey = await transport.get_one()
        return message, sender_verkey, recipient_verkey

    async def switch(self, message: Message) -> (bool, Message):
        async with self.__get_transport_lazy() as transport:
            if type(self.__to) is list:
                raise NotImplemented
            else:
                success, response = await transport.switch(message)
                return success, response

    async def abort(self):
        if self.__is_start:
            await self.__transport.stop()
            self.__is_start = False
        self.__transport = None
        await super().abort()

    @asynccontextmanager
    async def __get_transport_lazy(self):
        if self.__transport is None:
            async with _current_hub().get_agent_connection_lazy() as agent:
                self._agent = agent
                if self.__pthid is None:
                    self.__transport = await agent.spawn(self.__thid, self.__to)
                else:
                    self.__transport = await agent.spawn(self.__thid, self.__to, self.__pthid)
                await self.__transport.start(time_to_live=self.time_to_live)
                self.__is_start = True
        try:
            yield self.__transport
        except SiriusConnectionClosed:
            if self.is_aborted:
                raise OperationAbortedManually('User aborted operation')
            else:
                raise
