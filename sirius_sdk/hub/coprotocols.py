import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Any, Union, Tuple, Dict
from contextlib import asynccontextmanager

from sirius_sdk.agent.pairwise import Pairwise, TheirEndpoint
from sirius_sdk.agent.listener import Event
from sirius_sdk.messaging import Message
from sirius_sdk.errors.exceptions import SiriusContextError, OperationAbortedManually, SiriusConnectionClosed, \
    SiriusTimeoutIO

from .core import _current_hub


PLEASE_ACK_DECORATOR = '~please_ack'
THREAD_DECORATOR = '~thread'


class AbstractCoProtocol(ABC):

    def __init__(self, time_to_live: int = None):
        self.__time_to_live = time_to_live
        self.__is_aborted = False
        self._hub = None
        self._is_start = False
        self._transport = None

    def __del__(self):
        if self._is_start and self._hub:
            self._hub.run_soon(self._transport.stop())

    @property
    def time_to_live(self) -> Optional[int]:
        return self.__time_to_live

    @property
    def is_aborted(self) -> bool:
        return self.__is_aborted

    async def abort(self):
        if self._hub:
            self._hub.run_soon(self.clean())
            if not self.__is_aborted:
                self.__is_aborted = True
                await self._hub.abort()
                self._hub = None

    async def clean(self):
        if self._is_start:
            await self._transport.stop()
            self._is_start = False
        self._transport = None


class AbstractP2PCoProtocol(AbstractCoProtocol):

    def __init__(self, time_to_live: int = None):
        super().__init__(time_to_live)

    @abstractmethod
    async def send(self, message: Message):
        pass

    @abstractmethod
    async def get_one(self) -> (Optional[Message], str, Optional[str]):
        """Accumulate event from participant

        return: message, sender_verkey, recipient_verkey
        """
        pass

    @abstractmethod
    async def switch(self, message: Message) -> (bool, Message):
        pass


class CoProtocolP2PAnon(AbstractP2PCoProtocol):

    def __init__(self, my_verkey: str, endpoint: TheirEndpoint, protocols: List[str], time_to_live: int = None):
        if not protocols:
            raise SiriusContextError('You must set protocols list. It is empty for now!')
        super().__init__(time_to_live=time_to_live)
        self.__my_verkey = my_verkey
        self.__endpoint = endpoint
        self.__thread_id = None
        self.__protocols = protocols

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
        if self._transport is None:
            self._hub = _current_hub()
            async with self._hub.get_agent_connection_lazy() as agent:
                self._transport = await agent.spawn(self.__my_verkey, self.__endpoint)
                await self._transport.start(protocols=self.protocols, time_to_live=self.time_to_live)
                self._is_start = True
        try:
            yield self._transport
        except SiriusConnectionClosed:
            if self.is_aborted:
                raise OperationAbortedManually('User aborted operation')
            else:
                raise


class CoProtocolP2P(AbstractP2PCoProtocol):

    def __init__(self, pairwise: Pairwise, protocols: List[str], time_to_live: int = None):
        if not protocols:
            raise SiriusContextError('You must set protocols list. It is empty for now!')
        super().__init__(time_to_live=time_to_live)
        self.__pairwise = pairwise
        self.__thread_id = None
        self.__protocols = protocols

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
        if self._transport is None:
            self._hub = _current_hub()
            async with self._hub.get_agent_connection_lazy() as agent:
                self._transport = await agent.spawn(self.__pairwise)
                await self._transport.start(protocols=self.protocols, time_to_live=self.time_to_live)
                self._is_start = True
        try:
            yield self._transport
        except SiriusConnectionClosed:
            if self.is_aborted:
                raise OperationAbortedManually('User aborted operation')
            else:
                raise


class CoProtocolThreadedP2P(AbstractP2PCoProtocol):

    def __init__(self, thid: str, to: Pairwise, pthid: str = None, time_to_live: int = None):
        super().__init__(time_to_live=time_to_live)
        self.__thid = thid
        self.__pthid = pthid
        self.__to = to

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
            success, response = await transport.switch(message)
            return success, response

    @asynccontextmanager
    async def __get_transport_lazy(self):
        if self._transport is None:
            self._hub = _current_hub()
            async with self._hub.get_agent_connection_lazy() as agent:
                if self.__pthid is None:
                    self._transport = await agent.spawn(self.__thid, self.__to)
                else:
                    self._transport = await agent.spawn(self.__thid, self.__to, self.__pthid)
                await self._transport.start(time_to_live=self.time_to_live)
                self._is_start = True
        try:
            yield self._transport
        except SiriusConnectionClosed:
            if self.is_aborted:
                raise OperationAbortedManually('User aborted operation')
            else:
                raise


class CoProtocolThreadedTheirs(AbstractCoProtocol):

    def __init__(self, thid: str, theirs: List[Pairwise], pthid: str = None, time_to_live: int = None):
        if len(theirs) < 1:
            raise SiriusContextError('theirs is empty')
        super().__init__(time_to_live=time_to_live)
        self.__thid = thid
        self.__pthid = pthid
        self.__theirs = theirs
        self.__dids = [their.their.did for their in theirs]

    @property
    def theirs(self) -> List[Pairwise]:
        return self.__theirs

    async def send(self, message: Message) -> Dict[Pairwise, Tuple[bool, str]]:
        """Send message to given participants

        return: List[( str: participant-id, bool: message was successfully sent, str: endpoint response body )]
        """
        results = {}
        async with self.__get_transport_lazy() as transport:
            responses = await transport.send_many(message, self.__theirs)
        for p2p, response in zip(self.__theirs, responses):
            success, body = response
            results[p2p] = (success, body)
        return results

    async def get_one(self) -> Tuple[Optional[Pairwise], Optional[Message]]:
        """Read event from any of participants at given timeout

        return: (Pairwise: participant-id, Message: message from given participant)
        """
        async with self.__get_transport_lazy() as transport:
            try:
                message, sender_verkey, recipient_verkey = await transport.get_one()
            except SiriusTimeoutIO:
                return None, None
            else:
                p2p = self.__load_p2p_from_verkey(sender_verkey)
                return p2p, message

    async def switch(self, message: Message) -> Dict[Pairwise, Tuple[bool, Optional[Message]]]:
        """Switch state while participants at given timeout give responses

        return: {
            Pairwise: participant,
            (
              bool: message was successfully sent to participant,
              Message: response message from participant or Null if request message was not successfully sent
            )
        }
        """
        statuses = await self.send(message)
        # fill errors to result just now
        results = {p2p: (False, None) for p2p, stat in statuses.items() if stat[0] is True}
        # then work with success participants only
        success_theirs = {p2p: (False, None) for p2p, stat in statuses.items() if stat[0] is True}
        accum = 0
        while accum < len(success_theirs):
            p2p, message = await self.get_one()
            if p2p is None:
                break
            if p2p and p2p.their.did in self.__dids:
                success_theirs[p2p] = (True, message)
                accum += 1
        results.update(success_theirs)
        return results

    def __load_p2p_from_verkey(self, verkey: str) -> Optional[Pairwise]:
        for p2p in self.__theirs:
            if p2p.their.verkey == verkey:
                return p2p
        return None

    @asynccontextmanager
    async def __get_transport_lazy(self):
        if self._transport is None:
            async with _current_hub().get_agent_connection_lazy() as agent:
                if self.__pthid is None:
                    self._transport = await agent.spawn(self.__thid)
                else:
                    self._transport = await agent.spawn(self.__thid, self.__pthid)
                await self._transport.start(time_to_live=self.time_to_live)
                self._is_start = True
        try:
            yield self._transport
        except SiriusConnectionClosed:
            if self.is_aborted:
                raise OperationAbortedManually('User aborted operation')
            else:
                raise


async def open_communication(event: Event, time_to_live: int = None) -> Optional[AbstractP2PCoProtocol]:
    if event.pairwise is not None and event.message is not None:
        thread_id = None
        parent_thread_id = None
        if THREAD_DECORATOR in event.message:
            thread_id = event.message.get(THREAD_DECORATOR, {}).get('thid', None)
        if PLEASE_ACK_DECORATOR in event.message:
            parent_thread_id = thread_id
            thread_id = event.message.get(PLEASE_ACK_DECORATOR, {}).get('message_id', None) or event.message.id
        if thread_id:
            comm = CoProtocolThreadedP2P(
                thid=thread_id,
                to=event.pairwise,
                pthid=parent_thread_id,
                time_to_live=time_to_live
            )
        else:
            comm = CoProtocolP2P(
                pairwise=event.pairwise,
                protocols=[event.message.protocol],
                time_to_live=time_to_live
            )
        return comm
    else:
        return None
