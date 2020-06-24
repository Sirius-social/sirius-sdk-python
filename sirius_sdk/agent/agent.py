import sys
import asyncio
from typing import List, Union, Optional

from ..messaging import Message, Type
from ..encryption import P2PConnection
from ..errors.exceptions import *
from .pairwise import Pairwise
from .wallet.wallets import DynamicWallet
from .connections import AgentRPC, AgentEvents, BaseAgentConnection, Endpoint


PY_35 = sys.version_info >= (3, 5)
PY_352 = sys.version_info >= (3, 5, 2)


class CoProtocol:

    """Abstraction peer-to-peer application-level protocols in the context of interactions among agent-like things.

    Sirius SDK protocol is high-level abstraction over Sirius transport architecture.
    Approach advantages:
      - developer build smart-contract logic in block-style that is easy to maintain and control
      - human-friendly source code of state machines in procedural style
      - program that is running in separate coroutine: lightweight abstraction to start/kill/state-detection work thread
    See details:
      - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0003-protocols
      - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0008-message-id-and-threading
    """

    THREAD_DECORATOR = '~thread'

    def __init__(
            self, thid: str, server_address: str, credentials: bytes, p2p: P2PConnection,
            pthid: str=None, timeout: int=AgentRPC.IO_TIMEOUT
    ):
        self.__server_address = server_address
        self.__credentials = credentials
        self.__p2p = p2p
        self.__timeout = timeout
        self.__sender_order = 0
        self.__received_orders = {}
        self.__thid = thid
        self.__pthid = pthid
        self.__rpc = None
        self.__wallet = None

    async def start(self) -> DynamicWallet:
        self.__rpc = await AgentRPC.create(
            self.__server_address,
            self.__credentials,
            self.__p2p,
            self.__timeout
        )
        self.__wallet = DynamicWallet(self.__rpc)
        return self.__wallet

    async def stop(self):
        if self.__rpc:
            await self.__rpc.close()
        self.__wallet = None

    async def send(
            self, message: Message, their_vk: Union[List[str], str],
            endpoint: str, my_vk: Optional[str], routing_keys: Optional[List[str]]
    ) -> (bool, Message):
        """
        Send message and wait answer

        :param message: Message
          See details:
           - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0020-message-types
        :param their_vk: Verkey of recipient
        :param endpoint: Endpoint address of recipient
        :param my_vk: VerKEy of Sender (AuthCrypt mode)
          See details:
           - https://github.com/hyperledger/aries-rfcs/tree/master/features/0019-encryption-envelope#authcrypt-mode-vs-anoncrypt-mode
        :param routing_keys: Routing key of recipient
        :return: Tuple (
          OpSuccess: True if operation was end with success
          Response message Response message fron recipient
        )
        """
        try:
            self.__prepare_message(message)
            answer = await self.__rpc.send_message(
                message=message, their_vk=their_vk, endpoint=endpoint,
                my_vk=my_vk, routing_keys=routing_keys, 
                coprotocol=True, coprotocol_thid=self.__thid
            )
            typ = Type.from_str(answer.type)
            order = self.__received_orders.get(typ.doc_uri, 0)
            self.__received_orders[typ.doc_uri] = order + 1
            return True, answer
        except SiriusTimeoutIO:
            return False, None

    async def send_to(self, message: Message, to: Pairwise) -> (bool, Message):
        """
        Send message to estableshed Pairwise connection and wait answer

        :param message: Message
          See details:
           - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0020-message-types
        :param to: Established Pairwise connection
        :return: Tuple (
          OpSuccess: True if operation was end with success
          Response message Response message fron recipient
        )
        """
        return await self.send(
            message=message,
            their_vk=to.their.verkey,
            endpoint=to.their.endpoint,
            my_vk=to.me.verkey,
            routing_keys=to.their.routing_keys
        )

    async def post(
            self, message: Message, their_vk: Union[List[str], str],
            endpoint: str, my_vk: Optional[str], routing_keys: Optional[List[str]]
    ):
        """Post message and don't wait answer

        :param message: Message
          See details:
           - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0020-message-types
        :param their_vk: Verkey of recipient
        :param endpoint: Endpoint address of recipient
        :param my_vk: VerKEy of Sender (AuthCrypt mode)
          See details:
           - https://github.com/hyperledger/aries-rfcs/tree/master/features/0019-encryption-envelope#authcrypt-mode-vs-anoncrypt-mode
        :param routing_keys: Routing key of recipient
        """
        self.__prepare_message(message)
        await self.__rpc.send_message(
            message=message, their_vk=their_vk, endpoint=endpoint,
            my_vk=my_vk, routing_keys=routing_keys, coprotocol=False
        )

    async def post_to(self, message: Message, to: Pairwise):
        """Post message to Pairwise connection and don't wait answer

        :param message: Message
          See details:
           - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0020-message-types
        :param to: Established Pairwise connection
        """
        await self.post(
            message=message,
            their_vk=to.their.verkey,
            endpoint=to.their.endpoint,
            my_vk=to.me.verkey,
            routing_keys=to.their.routing_keys
        )

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


class Listener:

    def __init__(self, source: AgentEvents):
        self.__source = source

    async def get_one(self, timeout: int=None) -> Message:
        msg = await self.__source.pull(timeout)
        return msg

    if PY_35:
        def __aiter__(self):
            if not self.__source.is_open:
                raise SiriusConnectionClosed()
            return self

        # Old 3.5 versions require a coroutine
        if not PY_352:
            __aiter__ = asyncio.coroutine(__aiter__)

        @asyncio.coroutine
        def __anext__(self):
            """Asyncio iterator interface for listener

            Note:
                TopicAuthorizationFailedError and OffsetOutOfRangeError
                exceptions can be raised in iterator.
                All other KafkaError exceptions will be logged and not raised
            """
            while True:
                return (yield from self.get_one())


class Agent:
    """
    Agent connection in the self-sovereign identity ecosystem.

    Managing an identity is complex. It is implementation of tools to help you to develop SSI Smart-Contracts logic.
    See details:
      - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0004-agents
    """

    def __init__(
            self, server_address: str, credentials: bytes,
            p2p: P2PConnection, timeout: int=BaseAgentConnection.IO_TIMEOUT, loop: asyncio.AbstractEventLoop=None
    ):
        """
        :param server_address: example https://my-cloud-provider.com
        :param credentials: credentials that point websocket connection to your agent and server-side services like
          routing keys maintenance ant etc.
        :param p2p: encrypted connection to establish tunnel to Agent that is running on server-side
        """
        self.__server_address = server_address
        self.__credentials = credentials
        self.__p2p = p2p
        self.__rpc = None
        self.__events = None
        self.__wallet = None
        self.__timeout = timeout
        self.__loop = loop
        self.__endpoints = []

    @property
    def wallet(self) -> DynamicWallet:
        """Indy wallet keys/schemas/CredDefs maintenance"""
        return self.__wallet

    @property
    def endpoints(self) -> List[Endpoint]:
        if self.__rpc and self.__rpc.is_open:
            return self.__endpoints
        else:
            raise RuntimeError('Open Agent at first!')

    async def spawn(self, thid: str, timeout: int=None, pthid: str=None) -> CoProtocol:
        """Spawn parallel protocol thread in running program

        See details:
          - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0003-protocols
        """
        protocol = CoProtocol(
            thid=thid,
            server_address=self.__server_address,
            credentials=self.__credentials,
            p2p=self.__p2p,
            pthid=pthid,
            timeout=timeout
        )
        await protocol.start()
        return protocol

    async def open(self):
        self.__rpc = await AgentRPC.create(
            self.__server_address, self.__credentials, self.__p2p, self.__timeout, self.__loop
        )
        self.__endpoints = self.__rpc.endpoints
        self.__wallet = DynamicWallet(rpc=self.__rpc)

    async def subscribe(self) -> Listener:
        self.__events = await AgentEvents.create(
            self.__server_address, self.__credentials, self.__p2p, self.__timeout, self.__loop
        )
        return Listener(self.__events)

    async def close(self):
        if self.__rpc:
            await self.__rpc.close()
        if self.__events:
            await self.__events.close()
        self.__wallet = None

    async def ping(self) -> bool:
        success = await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/ping_agent'
        )
        return success

    async def send_message(
            self, message: Message, their_vk: Union[List[str], str],
            endpoint: str, my_vk: Optional[str], routing_keys: Optional[List[str]] = None
    ) -> (bool, Message):
        """
        Implementation of basicmessage feature
        See details:
          - https://github.com/hyperledger/aries-rfcs/tree/master/features/0095-basic-message

        :param message: Message
          See details:
           - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0020-message-types
        :param their_vk: Verkey of recipient
        :param endpoint: Endpoint address of recipient
        :param my_vk: VerKey of Sender (AuthCrypt mode)
          See details:
           - https://github.com/hyperledger/aries-rfcs/tree/master/features/0019-encryption-envelope#authcrypt-mode-vs-anoncrypt-mode
        :param routing_keys: Routing key of recipient
        """
        await self.__rpc.send_message(
            message=message, their_vk=their_vk, endpoint=endpoint,
            my_vk=my_vk, routing_keys=routing_keys, coprotocol=False
        )
