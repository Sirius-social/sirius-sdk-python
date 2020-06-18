from typing import List, Union, Optional

from ..messaging import Message, Type
from ..encryption import P2PConnection
from ..errors.exceptions import SiriusTimeoutIO
from .pairwise import Pairwise
from .wallet.wallets import DynamicWallet
from .connections import AgentRPC, AgentEvents


class CoProtocol:

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

    async def start(self):
        self.__rpc = await AgentRPC.create(
            self.__server_address,
            self.__credentials,
            self.__p2p,
            self.__timeout
        )

    async def stop(self):
        if self.__rpc:
            await self.__rpc.close()

    async def send(
            self, message: Message, their_vk: Union[List[str], str],
            endpoint: str, my_vk: Optional[str], routing_keys: Optional[List[str]]
    ) -> (bool, Message):
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
        self.__prepare_message(message)
        await self.__rpc.send_message(
            message=message, their_vk=their_vk, endpoint=endpoint,
            my_vk=my_vk, routing_keys=routing_keys, coprotocol=False
        )

    async def post_to(self, message: Message, to: Pairwise):
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


class Agent:

    def __init__(self, server_address: str, credentials: bytes, p2p: P2PConnection):
        self.__server_address = server_address
        self.__credentials = credentials
        self.__p2p = p2p
        self.__rpc = None
        self.__events = None
        self.__wallet = None

    @property
    def wallet(self) -> DynamicWallet:
        return self.__wallet

    async def spawn(self, thid: str, timeout: int=None, pthid: str=None) -> CoProtocol:
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
        self.__rpc = await AgentRPC.create(self.__server_address, self.__credentials, self.__p2p)
        self.__events = await AgentEvents.create(self.__server_address, self.__credentials, self.__p2p)
        self.__wallet = DynamicWallet(rpc=self.__rpc)

    async def close(self):
        if self.__rpc:
            await self.__rpc.close()
        if self.__events:
            await self.__events.close()
        self.__wallet = None
