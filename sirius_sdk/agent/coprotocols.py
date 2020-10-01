from abc import ABC
from typing import List, Optional
from datetime import datetime, timedelta

from sirius_sdk.errors.exceptions import *
from sirius_sdk.messaging import *
from sirius_sdk.messaging.fields import DIDField
from sirius_sdk.agent.wallet.wallets import DynamicWallet
from sirius_sdk.agent.connections import AgentRPC, RoutingBatch
from sirius_sdk.agent.pairwise import TheirEndpoint, Pairwise
from sirius_sdk.agent.microledgers import MicroledgerList
from sirius_sdk.agent.pairwise import AbstractPairwiseList, WalletPairwiseList


class AbstractCoProtocolTransport(ABC):
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
    PLEASE_ACK_DECORATOR = '~please_ack'

    SEC_PER_DAY = 86400
    SEC_PER_HOURS = 3600
    SEC_PER_MIN = 60

    def __init__(self, rpc: AgentRPC):
        """
        :param rpc: RPC (independent connection)
        """
        self.__time_to_live = None
        self._rpc = rpc
        self._check_protocols = True
        self._check_verkeys = False
        self.__default_timeout = rpc.timeout
        self.__wallet = DynamicWallet(self._rpc)
        self.__microledgers = MicroledgerList(api=self._rpc)
        self.__pairwise_list = WalletPairwiseList(api=(self.__wallet.pairwise, self.__wallet.did))
        self.__die_timestamp = None
        self.__their_vk = None
        self.__endpoint = None
        self.__my_vk = None
        self.__routing_keys = None
        self.__is_setup = False
        self.__protocols = []
        self.__please_ack_ids = []
        self.__is_started = False

    @property
    def protocols(self) -> List[str]:
        return self.__protocols

    @property
    def time_to_live(self) -> int:
        return self.__time_to_live

    @property
    def is_started(self) -> bool:
        return self.__is_started

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
    def microledgers(self) -> MicroledgerList:
        return self.__microledgers

    @property
    def pairwise_list(self) -> AbstractPairwiseList:
        return self.__pairwise_list

    @property
    def is_alive(self) -> bool:
        if self.__die_timestamp:
            return datetime.now() < self.__die_timestamp
        else:
            return False

    async def start(self, protocols: List[str], time_to_live: int=None):
        self.__protocols = protocols
        self.__time_to_live = time_to_live
        if self.__time_to_live:
            self.__die_timestamp = datetime.now() + timedelta(seconds=self.__time_to_live)
        else:
            self.__die_timestamp = None
        self.__is_started = True

    async def stop(self):
        self.__die_timestamp = None
        self.__is_started = False
        await self.__cleanup_context()

    async def switch(self, message: Message) -> (bool, Message):
        """Send Message to other-side of protocol and wait for response

        :param message: Protocol request
        :return: (success, Response)
        """
        if not self.__is_setup:
            raise SiriusPendingOperation('You must Setup protocol instance at first')
        try:
            self._rpc.timeout = self.__get_io_timeout()
            await self.__setup_context(message)
            try:
                event = await self._rpc.send_message(
                    message=message,
                    their_vk=self.__their_vk,
                    endpoint=self.__endpoint,
                    my_vk=self.__my_vk,
                    routing_keys=self.__routing_keys,
                    coprotocol=True
                )
            finally:
                await self.__cleanup_context(message)
            if self._check_verkeys:
                recipient_verkey = event.get('recipient_verkey', None)
                sender_verkey = event.get('sender_verkey')
                if recipient_verkey != self.__my_vk:
                    raise SiriusInvalidPayloadStructure(f'Unexpected recipient_verkey: {recipient_verkey}')
                if sender_verkey != self.__their_vk:
                    raise SiriusInvalidPayloadStructure(f'Unexpected sender_verkey: {sender_verkey}')
            payload = Message(event.get('message', {}))
            if payload:
                ok, message = restore_message_instance(payload)
                if not ok:
                    message = Message(payload)
                if self._check_protocols:
                    if Type.from_str(message.type).protocol not in self.protocols:
                        raise SiriusInvalidMessage('@type has unexpected protocol "%s"' % message.type.protocol)
                return True, message
            else:
                return False, None
        except SiriusTimeoutIO:
            return False, None

    async def get_one(self) -> (Optional[Message], str, Optional[str]):
        self._rpc.timeout = self.__get_io_timeout()
        event = await self._rpc.read_protocol_message()
        if 'message' in event:
            ok, message = restore_message_instance(event['message'])
            if not ok:
                message = Message(event['message'])
        else:
            message = None
        sender_verkey = event.get('sender_verkey', None)
        recipient_verkey = event.get('recipient_verkey', None)
        return message, sender_verkey, recipient_verkey

    async def send(self, message: Message):
        """Send message and don't wait answer

        :param message:
        :return:
        """
        if not self.__is_setup:
            raise SiriusPendingOperation('You must Setup protocol instance at first')
        self._rpc.timeout = self.__get_io_timeout()
        await self.__setup_context(message)
        await self._rpc.send_message(
            message=message,
            their_vk=self.__their_vk,
            endpoint=self.__endpoint,
            my_vk=self.__my_vk,
            routing_keys=self.__routing_keys,
            coprotocol=False
        )

    async def send_many(self, message: Message, to: List[Pairwise]) -> List[Any]:
        batches = [
            RoutingBatch(p.their.verkey, p.their.endpoint, p.me.verkey, p.their.routing_keys)
            for p in to
        ]
        if not self.__is_setup:
            raise SiriusPendingOperation('You must Setup protocol instance at first')
        self._rpc.timeout = self.__get_io_timeout()
        await self.__setup_context(message)
        results = await self._rpc.send_message_batched(
            message, batches
        )
        return results

    async def __setup_context(self, message: Message):
        if self.PLEASE_ACK_DECORATOR in message:
            ack_message_id = message.get(self.PLEASE_ACK_DECORATOR, {}).get('message_id', None) or message.id
            ttl = self.__get_io_timeout() or 3600
            await self._rpc.start_protocol_with_threads(
                threads=[ack_message_id], ttl=ttl
            )
            self.__please_ack_ids.append(ack_message_id)

    async def __cleanup_context(self, message: Message=None):
        if message:
            if self.PLEASE_ACK_DECORATOR in message:
                ack_message_id = message.get(self.PLEASE_ACK_DECORATOR, {}).get('message_id', None) or message.id
                await self._rpc.stop_protocol_with_threads(
                    threads=[ack_message_id], off_response=True
                )
                self.__please_ack_ids = [i for i in self.__please_ack_ids if i != ack_message_id]
        else:
            await self._rpc.stop_protocol_with_threads(
                threads=self.__please_ack_ids, off_response=True
            )
            self.__please_ack_ids.clear()

    def __get_io_timeout(self):
        if self.__die_timestamp:
            now = datetime.now()
            if now < self.__die_timestamp:
                delta = self.__die_timestamp - now
                return delta.days * self.SEC_PER_DAY + delta.seconds
            else:
                return 0
        else:
            return None


class TheirEndpointCoProtocolTransport(AbstractCoProtocolTransport):

    def __init__(
            self, my_verkey: str, endpoint: TheirEndpoint, rpc: AgentRPC
    ):
        super().__init__(rpc)
        self.__endpoint = endpoint
        self.__my_verkey = my_verkey
        self._setup(
            their_verkey=endpoint.verkey,
            endpoint=endpoint.endpoint,
            my_verkey=my_verkey,
            routing_keys=endpoint.routing_keys
        )

    async def start(self, protocols: List[str], time_to_live: int = None):
        await super().start(protocols, time_to_live)
        await self._rpc.start_protocol_for_p2p(
            sender_verkey=self.__my_verkey,
            recipient_verkey=self.__endpoint.verkey,
            protocols=self.protocols,
            ttl=time_to_live
        )

    async def stop(self):
        await super().stop()
        await self._rpc.stop_protocol_for_p2p(
            sender_verkey=self.__my_verkey,
            recipient_verkey=self.__endpoint.verkey,
            protocols=self.protocols,
            off_response=True
        )


class PairwiseCoProtocolTransport(AbstractCoProtocolTransport):

    def __init__(
            self, pairwise: Pairwise, rpc: AgentRPC
    ):
        super().__init__(rpc)
        self.__pairwise = pairwise
        self._setup(
            their_verkey=pairwise.their.verkey,
            endpoint=pairwise.their.endpoint,
            my_verkey=pairwise.me.verkey,
            routing_keys=pairwise.their.routing_keys
        )

    async def start(self, protocols: List[str], time_to_live: int=None):
        await super().start(protocols, time_to_live)
        await self._rpc.start_protocol_for_p2p(
            sender_verkey=self.__pairwise.me.verkey,
            recipient_verkey=self.__pairwise.their.verkey,
            protocols=self.protocols,
            ttl=time_to_live
        )

    async def stop(self):
        await super().stop()
        await self._rpc.stop_protocol_for_p2p(
            sender_verkey=self.__pairwise.me.verkey,
            recipient_verkey=self.__pairwise.their.verkey,
            protocols=self.protocols,
            off_response=True
        )


class ThreadBasedCoProtocolTransport(AbstractCoProtocolTransport):
    """CoProtocol based on ~thread decorator

    See details:
      - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0008-message-id-and-threading
    """

    def __init__(
            self, thid: str, pairwise: Optional[Pairwise], rpc: AgentRPC, pthid: str=None
    ):
        super().__init__(rpc)
        self.__thid = thid
        self.__pthid = pthid
        self.__sender_order = 0
        self.__received_orders = {}
        self.pairwise = pairwise

    @property
    def pairwise(self) -> Pairwise:
        return self.__pairwise

    @pairwise.setter
    def pairwise(self, value: Optional[Pairwise]):
        self.__pairwise = value
        if value:
            self.__their = value.their
            self._setup(
                their_verkey=value.their.verkey,
                endpoint=value.their.endpoint,
                my_verkey=value.me.verkey,
                routing_keys=value.their.routing_keys
            )
        else:
            self.__their = None
            self._setup('', '', None, None)

    async def start(self, protocols: List[str] = None, time_to_live: int = None):
        if protocols is None:
            self._check_protocols = False
        await super().start(protocols, time_to_live)
        await self._rpc.start_protocol_with_threading(self.__thid, time_to_live)

    async def stop(self):
        await super().stop()
        await self._rpc.stop_protocol_with_threading(self.__thid, True)

    async def switch(self, message: Message) -> (bool, Message):
        self.__prepare_message(message)
        ok, response = await super().switch(message)
        if ok:
            respond_sender_order = response.get('~thread', {}).get('sender_order', None)
            if respond_sender_order is not None and self.__their is not None:
                recipient = self.__their.did
                err = DIDField().validate(recipient)
                if err is None:
                    order = self.__received_orders.get(recipient, 0)
                    self.__received_orders[recipient] = max(order, respond_sender_order)
        return ok, response

    async def send(self, message: Message):
        self.__prepare_message(message)
        await super().send(message)

    async def send_many(self, message: Message, to: List[Pairwise]) -> List[Any]:
        self.__prepare_message(message)
        ret = await super().send_many(message, to)
        return ret

    def __prepare_message(self, message: Message):
        if self.THREAD_DECORATOR not in message:  # Don't rewrite existing ~thread decorator
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
