import asyncio
import logging
from enum import IntEnum
from abc import ABC, abstractmethod
from typing import List, Union, Optional
from urllib.parse import urlparse

from multipledispatch import dispatch

from sirius_sdk.messaging import Message
from sirius_sdk.encryption import P2PConnection
from sirius_sdk.storages import AbstractImmutableCollection
from sirius_sdk.agent.listener import Listener
from sirius_sdk.agent.pairwise import Pairwise, TheirEndpoint
from sirius_sdk.agent.wallet.wallets import DynamicWallet
from sirius_sdk.agent.ledger import Ledger
from sirius_sdk.agent.pairwise import AbstractPairwiseList, WalletPairwiseList
from sirius_sdk.agent.storages import InWalletImmutableCollection
from sirius_sdk.agent.microledgers.abstract import AbstractMicroledgerList
from sirius_sdk.agent.microledgers.impl import MicroledgerList
from sirius_sdk.agent.coprotocols import PairwiseCoProtocolTransport, ThreadBasedCoProtocolTransport, TheirEndpointCoProtocolTransport
from sirius_sdk.agent.connections import AgentRPC, AgentEvents, BaseAgentConnection, Endpoint


class TransportLayers(ABC):

    @dispatch(str, TheirEndpoint)
    @abstractmethod
    async def spawn(self, my_verkey: str, endpoint: TheirEndpoint) -> TheirEndpointCoProtocolTransport:
        raise NotImplemented

    @dispatch(Pairwise)
    @abstractmethod
    async def spawn(self, pairwise: Pairwise) -> PairwiseCoProtocolTransport:
        raise NotImplemented

    @dispatch(str, Pairwise)
    @abstractmethod
    async def spawn(self, thid: str, pairwise: Pairwise) -> ThreadBasedCoProtocolTransport:
        raise NotImplemented

    @dispatch(str)
    @abstractmethod
    async def spawn(self, thid: str) -> ThreadBasedCoProtocolTransport:
        raise NotImplemented

    @dispatch(str, Pairwise, str)
    @abstractmethod
    async def spawn(self, thid: str, pairwise: Pairwise, pthid: str) -> ThreadBasedCoProtocolTransport:
        raise NotImplemented

    @dispatch(str, str)
    @abstractmethod
    async def spawn(self, thid: str, pthid: str) -> ThreadBasedCoProtocolTransport:
        raise NotImplemented


class SpawnStrategy(IntEnum):
    PARALLEL = 1
    CONCURRENT = 2


class Agent(TransportLayers):
    """
    Agent connection in the self-sovereign identity ecosystem.

    Managing an identity is complex. It is implementation of tools to help you to develop SSI Smart-Contracts logic.
    See details:
      - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0004-agents
    """

    def __init__(
            self, server_address: str, credentials: bytes,
            p2p: P2PConnection, timeout: int = BaseAgentConnection.IO_TIMEOUT,
            loop: asyncio.AbstractEventLoop = None, storage: AbstractImmutableCollection = None,
            name: str = None, spawn_strategy: SpawnStrategy = SpawnStrategy.PARALLEL
    ):
        """
        :param server_address: example https://my-cloud-provider.com
        :param credentials: credentials that point websocket connection to your agent and server-side services like
          routing keys maintenance ant etc.
        :param p2p: encrypted connection to establish tunnel to Agent that is running on server-side
        """
        parsed = urlparse(server_address)
        if parsed.scheme not in ['https']:
            logging.warning('Endpoints has non secure scheme, you will have issues for Android/iOS devices')
        self.__server_address = server_address
        self.__credentials = credentials
        self.__p2p = p2p
        self.__rpc = None
        self.__events = None
        self.__wallet = None
        self.__timeout = timeout
        self.__loop = loop
        self.__endpoints = []
        self.__ledgers = {}
        self.__storage = storage
        self.__pairwise_list = None
        self.__microledgers = None
        self.__name = name
        self.__spawn_strategy = spawn_strategy

    @property
    def name(self) -> Optional[str]:
        return self.__name

    @property
    def is_open(self) -> bool:
        return self.__rpc is not None and self.__rpc.is_open

    @property
    def wallet(self) -> DynamicWallet:
        """Indy wallet keys/schemas/CredDefs maintenance"""
        self.__check_is_open()
        return self.__wallet

    def ledger(self, name: str) -> Optional[Ledger]:
        self.__check_is_open()
        return self.__ledgers.get(name, None)

    @property
    def endpoints(self) -> List[Endpoint]:
        self.__check_is_open()
        return self.__endpoints

    @property
    def microledgers(self) -> AbstractMicroledgerList:
        self.__check_is_open()
        return self.__microledgers

    @property
    def pairwise_list(self) -> AbstractPairwiseList:
        self.__check_is_open()
        return self.__pairwise_list

    @dispatch(str, TheirEndpoint)
    async def spawn(self, my_verkey: str, endpoint: TheirEndpoint) -> TheirEndpointCoProtocolTransport:
        if self.__spawn_strategy == SpawnStrategy.PARALLEL:
            rpc = await AgentRPC.create(
                self.__server_address, self.__credentials, self.__p2p, self.__timeout, self.__loop
            )
        else:
            rpc = self.__rpc
        return TheirEndpointCoProtocolTransport(
            my_verkey=my_verkey,
            endpoint=endpoint,
            rpc=rpc
        )

    @dispatch(Pairwise)
    async def spawn(self, pairwise: Pairwise) -> PairwiseCoProtocolTransport:
        if self.__spawn_strategy == SpawnStrategy.PARALLEL:
            rpc = await AgentRPC.create(
                self.__server_address, self.__credentials, self.__p2p, self.__timeout, self.__loop
            )
        else:
            rpc = self.__rpc
        return PairwiseCoProtocolTransport(
            pairwise=pairwise,
            rpc=rpc
        )

    @dispatch(str, Pairwise)
    async def spawn(self, thid: str, pairwise: Pairwise) -> ThreadBasedCoProtocolTransport:
        if self.__spawn_strategy == SpawnStrategy.PARALLEL:
            rpc = await AgentRPC.create(
                self.__server_address, self.__credentials, self.__p2p, self.__timeout, self.__loop
            )
        else:
            rpc = self.__rpc
        return ThreadBasedCoProtocolTransport(
            thid=thid,
            pairwise=pairwise,
            rpc=rpc
        )

    @dispatch(str)
    @abstractmethod
    async def spawn(self, thid: str) -> ThreadBasedCoProtocolTransport:
        if self.__spawn_strategy == SpawnStrategy.PARALLEL:
            rpc = await AgentRPC.create(
                self.__server_address, self.__credentials, self.__p2p, self.__timeout, self.__loop
            )
        else:
            rpc = self.__rpc
        return ThreadBasedCoProtocolTransport(
            thid=thid,
            pairwise=None,
            rpc=rpc
        )

    @dispatch(str, Pairwise, str)
    async def spawn(self, thid: str, pairwise: Pairwise, pthid: str) -> ThreadBasedCoProtocolTransport:
        if self.__spawn_strategy == SpawnStrategy.PARALLEL:
            rpc = await AgentRPC.create(
                self.__server_address, self.__credentials, self.__p2p, self.__timeout, self.__loop
            )
        else:
            rpc = self.__rpc
        return ThreadBasedCoProtocolTransport(
            thid=thid,
            pairwise=pairwise,
            rpc=rpc,
            pthid=pthid
        )

    @dispatch(str, str)
    @abstractmethod
    async def spawn(self, thid: str, pthid: str) -> ThreadBasedCoProtocolTransport:
        if self.__spawn_strategy == SpawnStrategy.PARALLEL:
            rpc = await AgentRPC.create(
                self.__server_address, self.__credentials, self.__p2p, self.__timeout, self.__loop
            )
        else:
            rpc = self.__rpc
        return ThreadBasedCoProtocolTransport(
            thid=thid,
            pairwise=None,
            rpc=rpc,
            pthid=pthid
        )

    async def open(self):
        self.__rpc = await AgentRPC.create(
            self.__server_address, self.__credentials, self.__p2p, self.__timeout, self.__loop
        )
        self.__endpoints = self.__rpc.endpoints
        self.__wallet = DynamicWallet(rpc=self.__rpc)
        if self.__storage is None:
            self.__storage = InWalletImmutableCollection(self.__wallet.non_secrets)
        for network in self.__rpc.networks:
            self.__ledgers[network] = Ledger(
                name=network, api=self.__wallet.ledger,
                issuer=self.__wallet.anoncreds, cache=self.__wallet.cache, storage=self.__storage
            )
        self.__pairwise_list = WalletPairwiseList(api=(self.__wallet.pairwise, self.__wallet.did))
        self.__microledgers = MicroledgerList(api=self.__rpc)

    async def subscribe(self) -> Listener:
        self.__check_is_open()
        self.__events = await AgentEvents.create(
            self.__server_address, self.__credentials, self.__p2p, self.__timeout, self.__loop
        )
        return Listener(self.__events, self.pairwise_list)

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
        self.__check_is_open()
        await self.__rpc.send_message(
            message=message, their_vk=their_vk, endpoint=endpoint,
            my_vk=my_vk, routing_keys=routing_keys, coprotocol=False
        )

    async def send_to(self, message: Message, to: Pairwise):
        """Implementation of basicmessage feature
        See details:
          - https://github.com/hyperledger/aries-rfcs/tree/master/features/0095-basic-message

        :param message: Message
          See details:
           - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0020-message-types
        :param to: Pairwise (P2P) connection that have been established outside
        """
        self.__check_is_open()
        await self.send_message(
            message=message,
            their_vk=to.their.verkey,
            endpoint=to.their.endpoint,
            my_vk=to.me.verkey,
            routing_keys=to.their.routing_keys
        )

    async def generate_qr_code(self, value: str) -> str:
        """Service for QR codes generation

        You may create PNG image for QR code to share it on Web or others.
        """
        self.__check_is_open()
        resp = await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/admin/1.0/generate_qr',
            params={
                'value': value
            }
        )
        return resp['url']

    async def acquire(self, resources: List[str], lock_timeout: float, enter_timeout: float = 3) -> (bool, List[str]):
        """Acquire N resources given by names

        :param resources: names of resources that you are going to lock
        :param lock_timeout: max timeout resources will be locked. Resources will be automatically unlocked on expire
        :param enter_timeout: timeout to wait resources are released
        """

        self.__check_is_open()
        success, busy = await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/admin/1.0/acquire',
            params={
                'names': resources,
                'enter_timeout': enter_timeout,
                'lock_timeout': lock_timeout
            }
        )
        return success, busy

    async def release(self):
        """Release earlier locked resources"""

        await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/admin/1.0/release'
        )

    async def reopen(self, kill_tasks: bool = False):
        self.__check_is_open()
        await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/reopen',
            params={
                'kill_tasks': kill_tasks
            }
        )

    def __check_is_open(self):
        if self.__rpc and self.__rpc.is_open:
            return self.__endpoints
        else:
            raise RuntimeError('Open Agent at first!')
