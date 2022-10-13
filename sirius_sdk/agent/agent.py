import asyncio
import logging
from enum import IntEnum
from abc import ABC, abstractmethod
from typing import List, Union, Optional, Any, Tuple
from urllib.parse import urlparse

from multipledispatch import dispatch

from sirius_sdk.messaging import Message
from sirius_sdk.errors.exceptions import SiriusConnectionClosed
from sirius_sdk.abstract.bus import AbstractBus
from sirius_sdk.abstract.api import APIContents, APICoProtocols, APINetworks, APIRouter, APIDistributedLocks, \
    APITransport, APICrypto
from sirius_sdk.abstract.batching import RoutingBatch
from sirius_sdk.encryption import P2PConnection
from sirius_sdk.abstract.storage import AbstractImmutableCollection
from sirius_sdk.agent.listener import Listener
from sirius_sdk.agent.wallet.wallets import DynamicWallet
from sirius_sdk.agent.dkms import DKMS
from sirius_sdk.agent.pairwise import AbstractPairwiseList, WalletPairwiseList
from sirius_sdk.agent.storages import InWalletImmutableCollection
from sirius_sdk.agent.microledgers.abstract import AbstractMicroledgerList
from sirius_sdk.agent.microledgers.impl import MicroledgerList
from sirius_sdk.agent.connections import AgentRPC, AgentEvents, BaseAgentConnection
from sirius_sdk.abstract.p2p import Endpoint, TheirEndpoint, Pairwise

from .bus import RpcBus


class SpawnStrategy(IntEnum):
    PARALLEL = 1
    CONCURRENT = 2


class Agent(APIContents, APICoProtocols, APINetworks, APIRouter, APITransport, APIDistributedLocks):
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
            name: str = None, spawn_strategy: SpawnStrategy = SpawnStrategy.PARALLEL,
            external_crypto: APICrypto = None
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
        self.__external_crypto_service = external_crypto
        self.__bus: Optional[AbstractBus] = None

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

    def dkms(self, name: str) -> Optional[DKMS]:
        self.__check_is_open()
        return self.__ledgers.get(name, None)

    @property
    def endpoints(self) -> List[Endpoint]:
        self.__check_is_open()
        return self.__endpoints

    @property
    def microledgers(self) -> Optional[AbstractMicroledgerList]:
        self.__check_is_open()
        return self.__microledgers

    @property
    def pairwise_list(self) -> AbstractPairwiseList:
        self.__check_is_open()
        return self.__pairwise_list

    @property
    def bus(self) -> Optional[AbstractBus]:
        return self.__bus

    async def spawn_coprotocol(self) -> AbstractBus:
        if self.__spawn_strategy == SpawnStrategy.PARALLEL:
            rpc = await AgentRPC.create(
                self.__server_address, self.__credentials, self.__p2p,
                self.__timeout, self.__loop, self.__external_crypto_service
            )
        else:
            rpc = self.__rpc
        bus = RpcBus(connector=rpc.connector, p2p=self.__p2p)
        return bus

    async def open(self):
        self.__rpc = await AgentRPC.create(
            self.__server_address, self.__credentials, self.__p2p,
            self.__timeout, self.__loop, self.__external_crypto_service
        )
        self.__bus = RpcBus(connector=self.__rpc.connector, p2p=self.__p2p)
        self.__endpoints = self.__rpc.endpoints
        self.__wallet = DynamicWallet(rpc=self.__rpc)
        if self.__storage is None:
            self.__storage = InWalletImmutableCollection(self.__wallet.non_secrets)
        for network in self.__rpc.networks:
            self.__ledgers[network] = DKMS(
                name=network, api=self.__wallet.ledger,
                issuer=self.__wallet.anoncreds, cache=self.__wallet.cache, storage=self.__storage
            )
        self.__pairwise_list = WalletPairwiseList(api=(self.__wallet.pairwise, self.__wallet.did))
        self.__microledgers = MicroledgerList(api=self.__rpc)

    async def subscribe(self, group_id: str = None) -> Listener:
        self.__check_is_open()
        if group_id:
            extra = {'group_id': group_id}
        else:
            extra = None
        self.__events = await AgentEvents.create(
            self.__server_address, self.__credentials, self.__p2p,
            self.__timeout, self.__loop, self.__external_crypto_service, extra
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

    async def send(
            self, message: Message, their_vk: Union[List[str], str],
            endpoint: str, my_vk: Optional[str] = None, routing_keys: Optional[List[str]] = None
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
        await self.send(
            message=message,
            their_vk=to.their.verkey,
            endpoint=to.their.endpoint,
            my_vk=to.me.verkey,
            routing_keys=to.their.routing_keys
        )

    async def send_batched(self, message: Message, batches: List[RoutingBatch]) -> List[Tuple[bool, str]]:
        self.__check_is_open()
        results = await self.__rpc.send_message_batched(message, batches)
        return results

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

    async def get_endpoints(self) -> List[Endpoint]:
        return self.endpoints

    async def reopen(self, kill_tasks: bool = False):
        self.__check_is_open()
        await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/reopen',
            params={
                'kill_tasks': kill_tasks
            }
        )

    async def echo(self, message: Any, data: Optional[Any] = None) -> Any:
        self.__check_is_open()
        params = {
            'message': message
        }
        if data:
            params['data'] = data
        ret = await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/admin/1.0/echo',
            params=params
        )
        return ret

    def __check_is_open(self):
        if self.__rpc and self.__rpc.is_open:
            return self.__endpoints
        else:
            raise SiriusConnectionClosed('Open Agent at first!')
