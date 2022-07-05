import asyncio
import json
from abc import ABC, abstractmethod
from typing import Optional, List, Any, Union, Tuple, Dict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from sirius_sdk.hub.core import Hub
from sirius_sdk.agent.pairwise import Pairwise, TheirEndpoint
from sirius_sdk.agent.listener import Event
from sirius_sdk.errors.exceptions import *
from sirius_sdk.messaging import Message
from sirius_sdk.messaging.fields import DIDField
from sirius_sdk.errors.exceptions import SiriusContextError, OperationAbortedManually, SiriusConnectionClosed, \
    SiriusTimeoutIO
from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage
from sirius_sdk.agent.aries_rfc.decorators import PLEASE_ACK_DECORATOR as ARIES_PLEASE_ACK_DECORATOR
from sirius_sdk.agent.aries_rfc.mixins import ThreadMixin

from .core import _current_hub


class AbstractCoProtocol(ABC):
    """Abstraction application-level protocols in the context of interactions among agent-like things.

        Sirius SDK protocol is high-level abstraction over Sirius transport architecture.
        Approach advantages:
          - developer build smart-contract logic in block-style that is easy to maintain and control
          - human-friendly source code of state machines in procedural style
          - program that is running in separate coroutine: lightweight abstraction to start/kill/state-detection work thread
        See details:
          - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0003-protocols
    """

    SEC_PER_DAY = 86400
    SEC_PER_HOURS = 3600
    SEC_PER_MIN = 60

    def __init__(self, time_to_live: int = None):
        self.__time_to_live = time_to_live
        self.__is_aborted = False
        self.__die_timestamp = None
        self._hub: Optional[Hub] = None
        self._is_running = False
        self._please_ack_ids = []

    def __del__(self):
        if self._is_running and self._hub:
            self._hub.run_soon(self.clean())

    @property
    def time_to_live(self) -> Optional[int]:
        """Time in seconds protocol will be connected to protocols Events Bus

         if None: protocol is infinite
        """
        return self.__time_to_live

    @property
    def is_alive(self) -> bool:
        """Protocol may running but ttl is out of date
        """
        if self.__die_timestamp and self._is_running:
            return datetime.now() < self.__die_timestamp
        else:
            return False

    @property
    def is_aborted(self) -> bool:
        """Protocol was aborted (forced terminated)"""
        return self.__is_aborted

    async def start(self):
        if self.__time_to_live:
            self.__die_timestamp = datetime.now() + timedelta(seconds=self.__time_to_live)
        else:
            self.__die_timestamp = None
        self._hub: Optional[Hub] = _current_hub()
        self._is_running = True

    async def stop(self):
        self._is_running = False

    async def abort(self):
        """Useful to Abort running co-protocol outside of current loop"""
        if self._hub:
            self._hub.run_soon(self.clean())
            if not self.__is_aborted:
                self.__is_aborted = True
                # Alarm! This call may kill all other co-protocols on the same Hub
                # await self._hub.abort()
                #
                self._hub = None

    async def clean(self):
        if self._is_running:
            await self.stop()
            self._is_running = False

    def _get_io_timeout(self):
        if self.__die_timestamp:
            now = datetime.now()
            if now < self.__die_timestamp:
                delta = self.__die_timestamp - now
                return delta.days * self.SEC_PER_DAY + delta.seconds
            else:
                return 0
        else:
            return None

    async def _setup_context(self, message: Message):
        bus = await self._hub.get_bus()
        ack_message_id = self._extract_ack_id(message)
        if ack_message_id:
            await bus.subscribe(ack_message_id)
            if ack_message_id not in self._please_ack_ids:
                self._please_ack_ids.append(ack_message_id)

    async def _cleanup_context(self, message: Message = None):
        bus = await self._hub.get_bus()
        if message:
            ack_message_id = self._extract_ack_id(message)
            if ack_message_id:
                await bus.unsubscribe(ack_message_id)
                self._please_ack_ids = [i for i in self._please_ack_ids if i != ack_message_id]
        else:
            await bus.unsubscribe_ext(self._please_ack_ids)
            self._please_ack_ids.clear()

    @staticmethod
    def _extract_ack_id(message: Message) -> Optional[str]:
        if isinstance(message, AriesProtocolMessage):
            if message.please_ack is True:
                return message.ack_message_id
        else:
            # If message has not-registered type
            if ARIES_PLEASE_ACK_DECORATOR in message:
                aries_msg = AriesProtocolMessage(**message)
                return aries_msg.ack_message_id
        return None


class AbstractP2PCoProtocol(AbstractCoProtocol):

    def __init__(self, protocols: List[str] = None, time_to_live: int = None):
        super().__init__(time_to_live)
        self.__their_vk: Optional[str] = None
        self.__endpoint: Optional[str] = None
        self.__my_vk: Optional[str] = None
        self.__routing_keys: Optional[List[str]] = None
        self.__protocols = protocols
        self.__is_setup = False
        self.__ack_thread_id = None
        self._binding_ids = []

    async def start(self):
        if not self.__is_setup:
            raise SiriusPendingOperation('You must Setup protocol instance at first')
        await super().start()
        await self._subscribe_to_events()
        # Remove duplicates
        self._binding_ids = list(set(self._binding_ids))

    async def stop(self):
        if self._binding_ids:
            bus = await self._hub.get_bus()
            await bus.unsubscribe_ext(self._binding_ids + self._please_ack_ids)
            self._binding_ids.clear()
            self._please_ack_ids.clear()
        await super().stop()

    async def send(self, message: Message):
        if not self.__is_setup:
            raise SiriusPendingOperation('You must Setup protocol instance at first')
        if not self._is_running:
            await self.start()
        async with _current_hub().get_agent_connection_lazy() as agent:
            await self._before(message, include_please_ack=False)
            await self._setup_context(message)
            await agent.send_message(
                message=message, their_vk=self.__their_vk, endpoint=self.__endpoint,
                my_vk=self.__my_vk, routing_keys=self.__routing_keys
            )

    async def get_one(self) -> (Optional[Message], str, Optional[str]):
        """Accumulate event from participant

        return: message, sender_verkey, recipient_verkey
        """
        if not self._is_running:
            await self.start()
        bus = await self._hub.get_bus()
        expected_binding_ids = self._binding_ids + self._please_ack_ids
        while True:
            # re-calc timeout in loop until event income
            timeout = self._get_io_timeout()
            if (timeout is not None) and (timeout <= 0):
                raise SiriusTimeoutIO
            # wait
            event = await bus.get_message(timeout=timeout)
            # process event
            if event.binding_id in expected_binding_ids:
                return event.message, event.sender_verkey, event.recipient_verkey
            else:
                # co-protocols are competitors, so
                # they operate in displace multitasking mode
                pass

    async def switch(self, message: Message) -> (bool, Message):
        """Send Message to other-side of protocol and wait for response

        :param message: Protocol request
        :return: (success, Response)
        """
        if not self.__is_setup:
            raise SiriusPendingOperation('You must Setup protocol instance at first')
        if not self._is_running:
            await self.start()
        try:
            await self._before(message, include_please_ack=True)
            await self._setup_context(message)
            try:
                await self.send(message)
                message, sender_verkey, recipient_verkey = await self.get_one()
                await self._after(message)
                return True, message
            finally:
                await self._cleanup_context(message)
        except SiriusTimeoutIO:
            return False, None

    async def _subscribe_to_events(self):
        bus = await self._hub.get_bus()
        ok, binding_ids = await bus.subscribe_ext(
            sender_vk=[self.__their_vk], recipient_vk=[self.__my_vk], protocols=self.__protocols
        )
        if ok:
            self._binding_ids.extend(binding_ids)
        else:
            raise SiriusRPCError('Error with subscribe to protocol events')

    def _setup(self, their_verkey: str, endpoint: str, my_verkey: str = None, routing_keys: List[str] = None):
        """Should be called in Descendant"""
        self.__their_vk = their_verkey
        self.__my_vk = my_verkey
        self.__endpoint = endpoint
        self.__routing_keys = routing_keys or []
        self.__is_setup = True

    async def _before(self, message: Message, include_please_ack: bool = True):
        if isinstance(message, AriesProtocolMessage):
            if include_please_ack and message.please_ack is False:
                message.please_ack = True
            if self.__ack_thread_id and not message.thread_id:  # Don't rewrite earlier set values
                message.thread_id = self.__ack_thread_id

    async def _after(self, message: Message):
        ack_id = self._extract_ack_id(message)
        if ack_id:
            self.__ack_thread_id = ack_id
        else:
            self.__ack_thread_id = None


class CoProtocolP2PAnon(AbstractP2PCoProtocol):

    def __init__(self, my_verkey: str, endpoint: TheirEndpoint, protocols: List[str], time_to_live: int = None):
        if not protocols:
            raise SiriusContextError('You must set protocols list. It is empty for now!')
        super().__init__(protocols=protocols, time_to_live=time_to_live)
        self._setup(their_verkey=endpoint.verkey, endpoint=endpoint.address, my_verkey=my_verkey)


class CoProtocolP2P(AbstractP2PCoProtocol):

    def __init__(self, pairwise: Pairwise, protocols: List[str], time_to_live: int = None):
        if not protocols:
            raise SiriusContextError('You must set protocols list. It is empty for now!')
        super().__init__(protocols=protocols, time_to_live=time_to_live)
        self._setup(their_verkey=pairwise.their.verkey, endpoint=pairwise.their.address, my_verkey=pairwise.me.verkey)


class CoProtocolThreadedP2P(AbstractP2PCoProtocol):

    def __init__(self, thid: str, to: Pairwise, pthid: str = None, time_to_live: int = None):
        super().__init__(time_to_live=time_to_live)
        self.__thid = thid
        self.__pthid = pthid
        self.__to = to
        self.__sender_order = 0
        self.__received_orders = {}
        self._setup(their_verkey=to.their.verkey, endpoint=to.their.address, my_verkey=to.me.verkey)

    async def _subscribe_to_events(self):
        bus = await self._hub.get_bus()
        ok = await bus.subscribe(thid=self.__thid)
        if ok:
            self._binding_ids.extend(self.__thid)
        else:
            raise SiriusRPCError('Error with subscribe to protocol events')

    async def _before(self, message: Message, include_please_ack: bool = True):
        thread = ThreadMixin.get_thread(message)
        if thread is None:
            thread = ThreadMixin.Thread(
                thid=self.__thid, pthid=self.__pthid,
                sender_order=self.__sender_order, received_orders=self.__received_orders
            )
            self.__sender_order += 1
            ThreadMixin.set_thread(message, thread)

    async def _after(self, message: Message):
        thread = ThreadMixin.get_thread(message)
        respond_sender_order = thread.sender_order if thread is not None else None
        if respond_sender_order is not None and self.__to is not None:
            recipient = self.__to.their.did
            err = DIDField().validate(recipient)
            if err is None:
                order = self.__received_orders.get(recipient, 0)
                self.__received_orders[recipient] = max(order, respond_sender_order)
