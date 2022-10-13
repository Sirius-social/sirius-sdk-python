import asyncio
import logging
from abc import ABC
from typing import Optional, List, Tuple, Dict
from datetime import datetime, timedelta

import sirius_sdk
from sirius_sdk.abstract.bus import AbstractBus
from sirius_sdk.abstract.listener import Event
from sirius_sdk.abstract.batching import RoutingBatch
from sirius_sdk.abstract.p2p import TheirEndpoint, Pairwise
from sirius_sdk.errors.exceptions import *
from sirius_sdk.messaging import Message
from sirius_sdk.messaging.fields import DIDField
from sirius_sdk.errors.exceptions import SiriusContextError, OperationAbortedManually, SiriusTimeoutIO
from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage
from sirius_sdk.agent.aries_rfc.decorators import PLEASE_ACK_DECORATOR as ARIES_PLEASE_ACK_DECORATOR
from sirius_sdk.agent.aries_rfc.mixins import ThreadMixin, PleaseAckMixin


def _qualify_did(value: str) -> str:
    if ':' not in value:
        return f'did:peer:{value}'
    else:
        return value


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
        self.__cur_loop: Optional[asyncio.AbstractEventLoop] = None
        self._bus: Optional[AbstractBus] = None
        self._is_running = False
        self._please_ack_ids = []

    def __del__(self):
        if self._is_running and self.__cur_loop and self.__cur_loop.is_running():
            asyncio.ensure_future(self.clean(), loop=self.__cur_loop)
            self.__cur_loop = None

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
        if not self._is_running:
            return False
        elif self.__die_timestamp:
            return datetime.now() < self.__die_timestamp
        else:
            return True

    @property
    def is_aborted(self) -> bool:
        """Protocol was aborted (forced terminated)"""
        return self.__is_aborted

    async def start(self):
        if self.__time_to_live:
            self.__die_timestamp = datetime.now() + timedelta(seconds=self.__time_to_live)
        else:
            self.__die_timestamp = None
        self.__cur_loop = asyncio.get_event_loop()
        self._bus = await sirius_sdk.spawn_coprotocol()
        self._is_running = True

    async def stop(self):
        self._is_running = False
        self.__cur_loop = None
        self._bus = None
        self._please_ack_ids.clear()

    async def abort(self):
        """Useful to Abort running co-protocol outside of current loop"""
        if not self.__is_aborted:
            self.__is_aborted = True
            await self.__abort()

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
        if isinstance(message, PleaseAckMixin):
            message.please_ack = True
        ack_message_id = self._extract_ack_id(message)
        if ack_message_id and ack_message_id not in self._please_ack_ids:
            await self._bus.subscribe(ack_message_id)
            self._please_ack_ids.append(ack_message_id)

    async def _cleanup_context(self, message: Message = None):
        if message:
            ack_message_id = self._extract_ack_id(message)
            if ack_message_id:
                await self._bus.unsubscribe(ack_message_id)
                self._please_ack_ids = [i for i in self._please_ack_ids if i != ack_message_id]
            thread = ThreadMixin.get_thread(message)
            if thread:
                if thread.thid in self._please_ack_ids:
                    await self._bus.unsubscribe(thread.thid)
                    self._please_ack_ids = [i for i in self._please_ack_ids if i != thread.thid]
        else:
            await self._bus.unsubscribe_ext(self._please_ack_ids)
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

    async def __abort(self):
        if self._bus:
            await self._bus.abort()


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

    @property
    def binding_ids(self) -> List[str]:
        return self._binding_ids

    async def start(self):
        if not self.__is_setup:
            raise SiriusPendingOperation('You must Setup protocol instance at first')
        await super().start()
        await self._subscribe_to_events()
        # Remove duplicates
        self._binding_ids = list(set(self._binding_ids))

    async def stop(self):
        if self._binding_ids or self._please_ack_ids:
            await self._bus.unsubscribe_ext(self._binding_ids + self._please_ack_ids)
            self._binding_ids.clear()
            self._please_ack_ids.clear()
        await super().stop()

    async def send(self, message: Message):
        if not self.__is_setup:
            raise SiriusPendingOperation('You must Setup protocol instance at first')
        if not self._is_running:
            await self.start()
        await self._before(message, include_please_ack=False)
        await self._setup_context(message)
        await sirius_sdk.send(
            message=message, their_vk=self.__their_vk, endpoint=self.__endpoint,
            my_vk=self.__my_vk, routing_keys=self.__routing_keys
        )

    async def get_one(self) -> (Optional[Message], str, Optional[str]):
        """Accumulate event from participant

        return: message, sender_verkey, recipient_verkey
        """
        if not self._is_running:
            await self.start()
        expected_binding_ids = self._binding_ids + self._please_ack_ids
        while True:
            # re-calc timeout in loop until event income
            timeout = self._get_io_timeout()
            if (timeout is not None) and (timeout <= 0):
                raise SiriusTimeoutIO
            # wait
            try:
                event = await self._bus.get_message(timeout=timeout)
            except OperationAbortedManually:
                await self.clean()
                raise
            # process event
            await self._after(event.message)
            if event.thread_id in expected_binding_ids:
                return event.message, event.sender_verkey, event.recipient_verkey
            else:
                # co-protocols are competitors, so
                # they operate in displace multitasking mode
                logging.warning(
                    f'Expected binding_id: "{expected_binding_ids}" actually "{event.thread_id}" was received'
                )

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
        ok, binding_ids = await self._bus.subscribe_ext(
            sender_vk=[self.__their_vk], recipient_vk=[self.__my_vk], protocols=self.__protocols
        )
        if ok:
            self._binding_ids.extend(binding_ids)
            self._binding_ids = list(set(self._binding_ids))
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
                thread = ThreadMixin.get_thread(message) or ThreadMixin.Thread()
                thread.thid = self.__ack_thread_id
                ThreadMixin.set_thread(message, thread)
                self.__ack_thread_id = None

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
        self._setup(
            their_verkey=endpoint.verkey, endpoint=endpoint.address,
            my_verkey=my_verkey, routing_keys=endpoint.routing_keys
        )


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
        self.__last_received_msg_id = {}
        recipient = _qualify_did(to.their.did)
        self.__received_orders[recipient] = 0
        self._setup(their_verkey=to.their.verkey, endpoint=to.their.address, my_verkey=to.me.verkey)

    @property
    def thid(self) -> str:
        return self.__thid

    async def _subscribe_to_events(self):
        ok = await self._bus.subscribe(thid=self.__thid)
        if ok:
            self._binding_ids.append(self.__thid)
            self._binding_ids = list(set(self._binding_ids))
        else:
            raise SiriusRPCError('Error with subscribe to protocol events')

    async def _before(self, message: Message, include_please_ack: bool = True):
        await super()._before(message, include_please_ack)
        thread = ThreadMixin.get_thread(message)
        if thread is None:  # Don't rewrite externally set thread values
            thread = ThreadMixin.Thread(
                thid=self.__thid, pthid=self.__pthid,
                sender_order=self.__sender_order, received_orders=dict(**self.__received_orders)
            )
            self.__sender_order += 1
            ThreadMixin.set_thread(message, thread)

    async def _after(self, message: Message):
        await super()._after(message)
        if self.__to is not None:
            recipient = _qualify_did(self.__to.their.did)
            err = DIDField().validate(recipient)
            if err is None:
                last_msg_id = self.__last_received_msg_id.get(recipient, None)
                if last_msg_id != message.id:
                    if recipient not in self.__received_orders:
                        order = 1
                    else:
                        order = self.__received_orders[recipient] + 1
                    self.__received_orders[recipient] = order
                    self.__last_received_msg_id[recipient] = message.id


class CoProtocolThreadedTheirs(AbstractCoProtocol):

    def __init__(self, thid: str, theirs: List[Pairwise], pthid: str = None, time_to_live: int = None):
        if len(theirs) < 1:
            raise SiriusContextError('theirs is empty')
        super().__init__(time_to_live=time_to_live)
        self.__thid = thid
        self.__pthid = pthid
        self.__theirs = theirs
        self.__dids = [their.their.did for their in theirs]
        self.__received_orders = {}
        for to in theirs:
            recipient = _qualify_did(to.their.did)
            self.__received_orders[recipient] = 0
        self.__last_received_msg_id = {}
        self.__sender_order = 0

    @property
    def theirs(self) -> List[Pairwise]:
        return self.__theirs

    async def start(self):
        await super().start()
        ok = await self._bus.subscribe(thid=self.__thid)
        if not ok:
            raise SiriusRPCError('Error with subscribe to protocol events')

    async def stop(self):
        binding_ids = [self.__thid] + self._please_ack_ids
        await self._bus.unsubscribe_ext(binding_ids)
        self._please_ack_ids.clear()
        await super().stop()

    async def send(self, message: Message) -> Dict[Pairwise, Tuple[bool, str]]:
        """Send message to given participants

        return: List[( str: participant-id, bool: message was successfully sent, str: endpoint response body )]
        """

        if not self._is_running:
            await self.start()

        batches = [
            RoutingBatch(p.their.verkey, p.their.endpoint, p.me.verkey, p.their.routing_keys)
            for p in self.__theirs
        ]

        await self._before(message)
        await self._setup_context(message)
        responses = await sirius_sdk.send_batched(message, batches)
        results = {}
        for p2p, response in zip(self.__theirs, responses):
            success, body = response
            results[p2p] = (success, body)
        return results

    async def get_one(self) -> Tuple[Optional[Pairwise], Optional[Message]]:
        """Read event from any of participants at given timeout

        return: (Pairwise: participant-id, Message: message from given participant)
        """
        if not self._is_running:
            await self.start()
        expected_thread_ids = [self.__thid] + self._please_ack_ids
        while True:
            # re-calc timeout in loop until event income
            timeout = self._get_io_timeout()
            if (timeout is not None) and (timeout <= 0):
                raise SiriusTimeoutIO
            # wait
            try:
                event = await self._bus.get_message(timeout=timeout)
            except SiriusTimeoutIO:
                return None, None
            except OperationAbortedManually:
                await self.clean()
                raise
            # process event
            if event.thread_id in expected_thread_ids:
                p2p = self.__load_p2p_from_verkey(event.sender_verkey)
                return p2p, event.message
            else:
                # co-protocols are competitors, so
                # they operate in displace multitasking mode
                logging.warning(
                    f'Expected thread_id: "{expected_thread_ids}" actually "{event.thread_id}" was received'
                )

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
        rcv_messages = []
        try:
            while accum < len(success_theirs):
                p2p, message = await self.get_one()
                if p2p is None:
                    break
                await self._after(message, p2p)
                if p2p and p2p.their.did in self.__dids:
                    success_theirs[p2p] = (True, message)
                    accum += 1
                rcv_messages.append(message)
            results.update(success_theirs)
            return results
        finally:
            await self._cleanup_contexts(rcv_messages)

    async def _before(self, message: Message):
        thread = ThreadMixin.get_thread(message)
        if thread is None:  # Don't rewrite externally set thread values
            thread = ThreadMixin.Thread(
                thid=self.__thid, pthid=self.__pthid,
                sender_order=self.__sender_order, received_orders=dict(**self.__received_orders)
            )
            ThreadMixin.set_thread(message, thread)

    async def _after(self, message: Message, p2p: Pairwise):
        recipient = _qualify_did(p2p.their.did)
        err = DIDField().validate(recipient)
        if err is None:
            last_msg_id = self.__last_received_msg_id.get(recipient, None)
            if last_msg_id != message.id:
                if recipient not in self.__received_orders:
                    order = 1
                else:
                    order = self.__received_orders[recipient] + 1
                self.__received_orders[recipient] = order
                self.__last_received_msg_id[recipient] = message.id

    async def _cleanup_contexts(self, messages: List[Message]):
        for msg in messages:
            await self._cleanup_context(msg)

    def __load_p2p_from_verkey(self, verkey: str) -> Optional[Pairwise]:
        for p2p in self.__theirs:
            if p2p.their.verkey == verkey:
                return p2p
        return None


def prepare_response(request: Message, response: Message):
    thread_id = None
    parent_thread_id = None
    thread = ThreadMixin.get_thread(request)
    if thread and thread.thid:
        thread_id = thread.thid
    ack_id = PleaseAckMixin.get_ack_message_id(request)
    if ack_id:
        parent_thread_id = thread_id
        thread_id = ack_id
    if thread_id:
        ThreadMixin.set_thread(
            response,
            value=ThreadMixin.Thread(thid=thread_id, pthid=parent_thread_id)
        )


async def open_communication(event: Event, time_to_live: int = None) -> Optional[AbstractP2PCoProtocol]:
    if event.pairwise is not None and event.message is not None:
        thread_id = None
        parent_thread_id = None
        thread = ThreadMixin.get_thread(event.message)
        if thread and thread.thid:
            thread_id = thread.thid
        ack_id = PleaseAckMixin.get_ack_message_id(event.message)
        if ack_id:
            parent_thread_id = thread_id
            thread_id = ack_id
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
