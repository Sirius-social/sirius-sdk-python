from abc import ABC, abstractmethod
from typing import List
from datetime import datetime, timedelta

from ..errors.exceptions import *
from ..encryption import P2PConnection
from ..messaging import Message, Type
from .wallet.wallets import DynamicWallet
from .connections import AgentRPC
from .pairwise import TheirEndpoint, Pairwise


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

    THREAD_DECORATOR = '~thread'

    SEC_PER_DAY = 86400
    SEC_PER_HOURS = 3600
    SEC_PER_MIN = 60

    def __init__(self, rpc: AgentRPC, time_to_live: int=None):
        """
        :param rpc: RPC (independent connection)
        :param time_to_live: (seconds) time to live for protocol
        """
        self.__time_to_live = time_to_live
        self._rpc = rpc
        self.__default_timeout = rpc.timeout
        self.__wallet = DynamicWallet(self._rpc)
        self.__die_timestamp = None
        self.__their_vk = None
        self.__endpoint = None
        self.__my_vk = None
        self.__routing_keys = None
        self.__is_setup = False

    def _setup(self, their_verkey: str, endpoint: str, my_verkey: str=None, routing_keys: List[str]=None):
        """Should be called in Descendant"""
        self.__their_vk = their_verkey
        self.__my_vk = my_verkey
        self.__endpoint = endpoint
        self.__routing_keys = routing_keys or []
        self.__is_setup = True

    @property
    def wallet(self) -> DynamicWallet:
        return self.__wallet

    @property
    def is_alive(self) -> bool:
        if self.__die_timestamp:
            return datetime.now() < self.__die_timestamp
        else:
            return False

    async def start(self):
        if self.__time_to_live:
            self.__die_timestamp = datetime.now() + timedelta(seconds=self.__time_to_live)
        else:
            self.__die_timestamp = None

    async def stop(self):
        self.__die_timestamp = None

    async def switch(self, request: Message) -> (bool, Message):
        """Send Message to other-side of protocol and wait for response

        :param request: Protocol request
        :return: (success, Response)
        """
        if not self.__is_setup:
            raise SiriusPendingOperation('You must Setup protocol instance at first')
        try:
            self._rpc.timeout = self.__get_io_timeout()
            answer = await self._rpc.send_message(
                message=request,
                their_vk=self.__their_vk,
                endpoint=self.__endpoint,
                my_vk=self.__my_vk,
                routing_keys=self.__routing_keys,
                coprotocol=True
            )
            return True, answer
        except SiriusTimeoutIO:
            return False, None

    async def send(self, message: Message):
        """Send message and don't wait answer

        :param message:
        :return:
        """
        if not self.__is_setup:
            raise SiriusPendingOperation('You must Setup protocol instance at first')
        self._rpc.timeout = self.__default_timeout
        await self._rpc.send_message(
            message=message,
            their_vk=self.__their_vk,
            endpoint=self.__endpoint,
            my_vk=self.__my_vk,
            routing_keys=self.__routing_keys,
            coprotocol=False
        )

    def __get_io_timeout(self):
        if self.__die_timestamp:
            now = datetime.now()
            if now < self.__die_timestamp:
                delta = self.__die_timestamp - now
                return delta.day * self.SEC_PER_DAY + delta.hour * self.SEC_PER_HOURS + \
                       delta.minute * self.SEC_PER_MIN + delta.second
            else:
                return 0
        else:
            return None


class TheirEndpointCoProtocol(AbstractCoProtocol):

    def __init__(
            self, my_verkey: str, endpoint: TheirEndpoint, msg_types: List[str], rpc: AgentRPC, time_to_live: int=None
    ):
        super().__init__(rpc, time_to_live)
        self.__endpoint = endpoint
        self.__my_verkey = my_verkey
        self.__msg_types = msg_types
        self._setup(
            their_verkey=endpoint.verkey,
            endpoint=endpoint.endpoint,
            my_verkey=my_verkey,
            routing_keys=endpoint.routing_keys
        )

    async def start(self):
        await super().start()
        await self._rpc.start_protocol_for_p2p(
            sender_verkey=self.__my_verkey,
            recipient_verkey=self.__endpoint.verkey,
            msg_types=self.__msg_types
        )

    async def stop(self):
        await super().stop()
        await self._rpc.start_protocol_for_p2p(
            sender_verkey=self.__my_verkey,
            recipient_verkey=self.__endpoint.verkey,
            msg_types=self.__msg_types
        )


class PairwiseProtocol(AbstractCoProtocol):

    def __init__(
            self, pairwise: Pairwise, msg_types: List[str], rpc: AgentRPC, time_to_live: int=None
    ):
        super().__init__(rpc, time_to_live)
        self.__pairwise = pairwise
        self.__msg_types = msg_types
        self._setup(
            their_verkey=pairwise.their.verkey,
            endpoint=pairwise.their.endpoint,
            my_verkey=pairwise.me.verkey,
            routing_keys=pairwise.their.routing_keys
        )

    async def start(self):
        await super().start()
        await self._rpc.start_protocol_for_p2p(
            sender_verkey=self.__pairwise.me.verkey,
            recipient_verkey=self.__pairwise.their.verkey,
            msg_types=self.__msg_types
        )

    async def stop(self):
        await super().stop()
        await self._rpc.start_protocol_for_p2p(
            sender_verkey=self.__pairwise.me.verkey,
            recipient_verkey=self.__pairwise.their.verkey,
            msg_types=self.__msg_types
        )


class ThreadBasedProtocol(AbstractCoProtocol):
    """CoProtocol based on ~thread decorator

    See details:
      - - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0008-message-id-and-threading
    """

    def __init__(
            self, thid: str, pairwise: Pairwise, rpc: AgentRPC, time_to_live: int=None, pthid: str=None
    ):
        super().__init__(rpc, time_to_live)
        self.__thid = thid
        self.__pthid = pthid
        self.__sender_order = 0
        self.__received_orders = {}
        self._setup(
            their_verkey=pairwise.their.verkey,
            endpoint=pairwise.their.endpoint,
            my_verkey=pairwise.me.verkey,
            routing_keys=pairwise.their.routing_keys
        )

    async def start(self):
        await super().start()
        await self._rpc.start_protocol_with_threading(self.__thid)

    async def stop(self):
        await super().stop()
        await self._rpc.stop_protocol_with_threading(self.__thid)

    async def switch(self, request: Message) -> (bool, Message):
        self.__prepare_message(request)
        return await self.switch(request)

    async def send(self, message: Message):
        self.__prepare_message(message)
        await self.send(message)

    def __prepare_message(self, message: Message):
        thread_decorator = {
            'thid': self.__thid,
            'sender_order': self.__sender_order
        }
        if self.__pthid:
            thread_decorator['pthid'] = self.__pthid
        if self.__received_orders:
            thread_decorator['received_orders'] = self.__received_orders
        self.__sender_order += 1
        message[self.THREAD_DECORATOR] = thread_decorator
