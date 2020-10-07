import asyncio
import contextvars
import threading
from abc import ABC, abstractmethod
from typing import Optional, List, Union, Any
from contextlib import asynccontextmanager

from sirius_sdk.encryption.p2p import P2PConnection
from sirius_sdk.errors.exceptions import SiriusInitializationError
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.agent.wallet.abstract.crypto import AbstractCrypto
from sirius_sdk.agent.wallet.abstract.did import AbstractDID
from sirius_sdk.agent.pairwise import Pairwise, TheirEndpoint
from sirius_sdk.messaging import Message
from sirius_sdk.agent.ledger import Ledger
from sirius_sdk.agent.listener import Listener
from sirius_sdk.agent.connections import Endpoint
from sirius_sdk.storages import AbstractImmutableCollection
from sirius_sdk.agent.microledgers import AbstractMicroledgerList, LedgerMeta, Transaction, AbstractMicroledger
from sirius_sdk.agent.coprotocols import TheirEndpointCoProtocolTransport, PairwiseCoProtocolTransport
from sirius_sdk.agent.agent import Agent, BaseAgentConnection


ROOT_HUB = None
THREAD_LOCAL_HUB = threading.local()
COROUTINE_LOCAL_HUB = contextvars.ContextVar('hub')


class Hub:

    def __init__(
            self, server_uri: str, credentials: bytes, p2p: P2PConnection, io_timeout: int = None,
            storage: AbstractImmutableCollection = None, crypto: AbstractCrypto = None,
            microledgers: AbstractMicroledgerList = None, pairwise_storage: AbstractPairwiseList = None,
            did: AbstractDID = None, loop: asyncio.AbstractEventLoop = None
    ):
        self.__crypto = crypto
        self.__microledgers = microledgers
        self.__pairwise_storage = pairwise_storage
        self.__did = did
        self.__server_uri = server_uri
        self.__credentials = credentials
        self.__p2p = p2p
        self.__agent = Agent(
            server_address=server_uri,
            credentials=credentials,
            p2p=p2p,
            timeout=io_timeout or BaseAgentConnection.IO_TIMEOUT,
            loop=loop,
            storage=storage,
        )

    def __del__(self):
        if self.__agent.is_open:
            asyncio.ensure_future(self.__agent.close())

    def copy(self):
        inst = Hub(
            server_uri=self.__server_uri, credentials=self.__credentials, p2p=self.__p2p
        )
        inst.__crypto = self.__crypto
        inst.__microledgers = self.__microledgers
        inst.__pairwise_storage = self.__pairwise_storage
        inst.__did = self.__did
        inst.__agent = self.__agent
        return inst

    @asynccontextmanager
    async def get_agent_connection_lazy(self):
        if not self.__agent.is_open:
            await self.__agent.open()
        yield self.__agent

    async def open(self):
        async with self.get_agent_connection_lazy() as agent:
            pass

    async def close(self):
        if self.__agent.is_open:
            await self.__agent.close()

    async def get_crypto(self) -> AbstractCrypto:
        async with self.get_agent_connection_lazy() as agent:
            return self.__crypto or agent.wallet.crypto

    async def get_microledgers(self) -> AbstractMicroledgerList:
        async with self.get_agent_connection_lazy() as agent:
            return self.__microledgers or agent.microledgers

    async def get_pairwise_list(self) -> AbstractPairwiseList:
        async with self.get_agent_connection_lazy() as agent:
            return self.__pairwise_storage or agent.pairwise_list

    async def get_did(self) -> AbstractDID:
        async with self.get_agent_connection_lazy() as agent:
            return self.__did or agent.wallet.did


def init(server_uri: str, credentials: bytes, p2p: P2PConnection, io_timeout: int = None,
         storage: AbstractImmutableCollection = None,
         crypto: AbstractCrypto = None, microledgers: AbstractMicroledgerList = None,
         did: AbstractDID = None, pairwise_storage: AbstractPairwiseList = None
         ):
    global ROOT_HUB
    root = Hub(
        server_uri=server_uri, credentials=credentials, p2p=p2p, io_timeout=io_timeout,
        storage=storage, crypto=crypto, microledgers=microledgers,
        pairwise_storage=pairwise_storage, did=did
    )
    loop = asyncio.get_event_loop()
    if loop.is_running():
        raise SiriusInitializationError('You must call this method outside coroutine')
    loop.run_until_complete(root.open())
    ROOT_HUB = root


@asynccontextmanager
async def context(
          server_uri: str, credentials: bytes, p2p: P2PConnection, io_timeout: int = None,
          storage: AbstractImmutableCollection = None,
          crypto: AbstractCrypto = None, microledgers: AbstractMicroledgerList = None,
          did: AbstractDID = None, pairwise_storage: AbstractPairwiseList = None
):
    hub = Hub(
        server_uri=server_uri, credentials=credentials, p2p=p2p, io_timeout=io_timeout,
        storage=storage, crypto=crypto, microledgers=microledgers,
        pairwise_storage=pairwise_storage, did=did
    )
    old_hub = __get_thread_local_gub()
    THREAD_LOCAL_HUB.instance = hub
    try:
        await hub.open()
        old_hub_coro = COROUTINE_LOCAL_HUB.get(None)
        token = COROUTINE_LOCAL_HUB.set(hub)
        try:
            yield
        finally:
            COROUTINE_LOCAL_HUB.reset(token)
            await hub.close()
            COROUTINE_LOCAL_HUB.set(old_hub_coro)
    finally:
        THREAD_LOCAL_HUB.instance = old_hub


def __get_root_hub() -> Optional[Hub]:
    return ROOT_HUB


def __get_thread_local_gub() -> Optional[Hub]:
    # For now thread local context not used but code prepared for future purposes
    try:
        inst = THREAD_LOCAL_HUB.instance
    except AttributeError:
        inst = None
    return inst


def _current_hub() -> Hub:
    inst = COROUTINE_LOCAL_HUB.get(None)
    if inst is None:
        root_hub = __get_thread_local_gub() or __get_root_hub()
        if root_hub is None:
            raise SiriusInitializationError('Non initialized Sirius Agent connection')
        inst = root_hub.copy()
        COROUTINE_LOCAL_HUB.set(inst)
    return inst


async def ledger(name: str) -> Optional[Ledger]:
    async with _current_hub().get_agent_connection_lazy() as agent:
        return agent.ledger(name)


async def endpoints() -> List[Endpoint]:
    async with _current_hub().get_agent_connection_lazy() as agent:
        return agent.endpoints


async def subscribe() -> Listener:
    async with _current_hub().get_agent_connection_lazy() as agent:
        return await agent.subscribe()


async def ping() -> bool:
    async with _current_hub().get_agent_connection_lazy() as agent:
        return await agent.ping()


async def send(
        message: Message, their_vk: Union[List[str], str],
        endpoint: str, my_vk: Optional[str], routing_keys: Optional[List[str]] = None
):
    async with _current_hub().get_agent_connection_lazy() as agent:
        await agent.send_message(
            message=message, their_vk=their_vk,
            endpoint=endpoint, my_vk=my_vk, routing_keys=routing_keys
        )


async def send_to(message: Message, to: Pairwise):
    async with _current_hub().get_agent_connection_lazy() as agent:
        await agent.send_to(message=message, to=to)


async def generate_qr_code(value: str) -> str:
    async with _current_hub().get_agent_connection_lazy() as agent:
        return await agent.generate_qr_code(value)


class DIDProxy(AbstractDID):

    async def create_and_store_my_did(self, did: str = None, seed: str = None, cid: bool = None) -> (str, str):
        service = await _current_hub().get_did()
        return await service.create_and_store_my_did(
            did=did, seed=seed, cid=cid
        )

    async def store_their_did(self, did: str, verkey: str = None) -> None:
        service = await _current_hub().get_did()
        return await service.store_their_did(
            did=did, verkey=verkey
        )

    async def set_did_metadata(self, did: str, metadata: dict = None) -> None:
        service = await _current_hub().get_did()
        return await service.set_did_metadata(
            did=did, metadata=metadata
        )

    async def list_my_dids_with_meta(self) -> List[Any]:
        service = await _current_hub().get_did()
        return await service.list_my_dids_with_meta()

    async def get_did_metadata(self, did) -> Optional[dict]:
        service = await _current_hub().get_did()
        return await service.get_did_metadata(did=did)

    async def key_for_local_did(self, did: str) -> str:
        service = await _current_hub().get_did()
        return await service.key_for_local_did(did=did)

    async def key_for_did(self, pool_name: str, did: str) -> str:
        service = await _current_hub().get_did()
        return await service.key_for_did(pool_name=pool_name, did=did)

    async def create_key(self, seed: str = None) -> str:
        service = await _current_hub().get_did()
        return await service.create_key(seed=seed)

    async def replace_keys_start(self, did: str, seed: str = None) -> str:
        service = await _current_hub().get_did()
        return await service.replace_keys_start(did=did, seed=seed)

    async def replace_keys_apply(self, did: str) -> None:
        service = await _current_hub().get_did()
        await service.replace_keys_apply(did=did)

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        service = await _current_hub().get_did()
        await service.set_key_metadata(verkey=verkey, metadata=metadata)

    async def get_key_metadata(self, verkey: str) -> dict:
        service = await _current_hub().get_did()
        return await service.get_key_metadata(verkey=verkey)

    async def set_endpoint_for_did(self, did: str, address: str, transport_key: str) -> None:
        service = await _current_hub().get_did()
        await service.set_endpoint_for_did(did=did, address=address, transport_key=transport_key)

    async def get_endpoint_for_did(self, pool_name: str, did: str) -> (str, Optional[str]):
        service = await _current_hub().get_did()
        return await service.get_endpoint_for_did(pool_name=pool_name, did=did)

    async def get_my_did_with_meta(self, did: str) -> Any:
        service = await _current_hub().get_did()
        return await service.get_my_did_with_meta(did=did)

    async def abbreviate_verkey(self, did: str, full_verkey: str) -> str:
        service = await _current_hub().get_did()
        return await service.abbreviate_verkey(did=did, full_verkey=full_verkey)

    async def qualify_did(self, did: str, method: str) -> str:
        service = await _current_hub().get_did()
        return await service.qualify_did(did=did, method=method)


class CryptoProxy(AbstractCrypto):

    async def create_key(self, seed: str = None, crypto_type: str = None) -> str:
        service = await _current_hub().get_crypto()
        return await service.create_key(seed=seed, crypto_type=crypto_type)

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        service = await _current_hub().get_crypto()
        return await service.set_key_metadata(verkey=verkey, metadata=metadata)

    async def get_key_metadata(self, verkey: str) -> Optional[dict]:
        service = await _current_hub().get_crypto()
        return await service.get_key_metadata(verkey=verkey)

    async def crypto_sign(self, signer_vk: str, msg: bytes) -> bytes:
        service = await _current_hub().get_crypto()
        return await service.crypto_sign(signer_vk=signer_vk, msg=msg)

    async def crypto_verify(self, signer_vk: str, msg: bytes, signature: bytes) -> bool:
        service = await _current_hub().get_crypto()
        return await service.crypto_verify(signer_vk=signer_vk, msg=msg, signature=signature)

    async def anon_crypt(self, recipient_vk: str, msg: bytes) -> bytes:
        service = await _current_hub().get_crypto()
        return await service.anon_crypt(recipient_vk=recipient_vk, msg=msg)

    async def anon_decrypt(self, recipient_vk: str, encrypted_msg: bytes) -> bytes:
        service = await _current_hub().get_crypto()
        return await service.anon_decrypt(recipient_vk=recipient_vk, encrypted_msg=encrypted_msg)

    async def pack_message(self, message: Any, recipient_verkeys: list, sender_verkey: str = None) -> bytes:
        service = await _current_hub().get_crypto()
        return await service.pack_message(
            message=message, recipient_verkeys=recipient_verkeys, sender_verkey=sender_verkey
        )

    async def unpack_message(self, jwe: bytes) -> dict:
        service = await _current_hub().get_crypto()
        return await service.unpack_message(jwe=jwe)


class MicroledgersProxy(AbstractMicroledgerList):

    async def create(
            self, name: str, genesis: Union[List[Transaction], List[dict]]
    ) -> (AbstractMicroledger, List[Transaction]):
        service = await _current_hub().get_microledgers()
        return await service.create(name, genesis)

    async def ledger(self, name: str) -> AbstractMicroledger:
        service = await _current_hub().get_microledgers()
        return await service.ledger(name)

    async def reset(self, name: str):
        service = await _current_hub().get_microledgers()
        await service.reset(name)

    async def is_exists(self, name: str):
        service = await _current_hub().get_microledgers()
        return await service.is_exists(name)

    async def leaf_hash(self, txn: Union[Transaction, bytes]) -> bytes:
        service = await _current_hub().get_microledgers()
        return await service.leaf_hash(txn)

    async def list(self) -> List[LedgerMeta]:
        service = await _current_hub().get_microledgers()
        return await service.list()


class PairwiseProxy(AbstractPairwiseList):

    async def create(self, pairwise: Pairwise):
        service = await _current_hub().get_pairwise_list()
        await service.create(pairwise)

    async def update(self, pairwise: Pairwise):
        service = await _current_hub().get_pairwise_list()
        await service.update(pairwise)

    async def is_exists(self, their_did: str) -> bool:
        service = await _current_hub().get_pairwise_list()
        return await service.is_exists(their_did)

    async def ensure_exists(self, pairwise: Pairwise):
        service = await _current_hub().get_pairwise_list()
        await service.ensure_exists(pairwise)

    async def load_for_did(self, their_did: str) -> Optional[Pairwise]:
        service = await _current_hub().get_pairwise_list()
        return await service.load_for_did(their_did)

    async def load_for_verkey(self, their_verkey: str) -> Optional[Pairwise]:
        service = await _current_hub().get_pairwise_list()
        return await service.load_for_verkey(their_verkey)


DID: AbstractDID = DIDProxy()
Crypto: AbstractCrypto = CryptoProxy()
Microledgers: AbstractMicroledgerList = MicroledgersProxy()
PairwiseList: AbstractPairwiseList = PairwiseProxy()


class AbstractCoProtocol(ABC):

    def __init__(self, time_to_live: int = None):
        self.__time_to_live = time_to_live
        self.__is_start = False

    @property
    def time_to_live(self) -> Optional[int]:
        return self.__time_to_live

    @abstractmethod
    async def send(self, message: Message):
        pass

    @abstractmethod
    async def switch(self, message: Message) -> (bool, Message):
        pass


class CoProtocolAnon(AbstractCoProtocol):

    def __init__(self, my_verkey: str, endpoint: TheirEndpoint, time_to_live: int = None):
        super().__init__(time_to_live=time_to_live)
        self.__is_start = False
        self.__transport = None
        self.__my_verkey = my_verkey
        self.__endpoint = endpoint

    def __del__(self):
        if self.__is_start:
            asyncio.ensure_future(self.__transport.stop())

    async def send(self, message: Message):
        async with self.__get_transport_lazy() as transport:
            await transport.send(message)

    async def switch(self, message: Message) -> (bool, Message):
        async with self.__get_transport_lazy() as transport:
            success, response = await transport.switch(message)
        return success, response

    @asynccontextmanager
    async def __get_transport_lazy(self) -> TheirEndpointCoProtocolTransport:
        if self.__transport is None:
            async with _current_hub().get_agent_connection_lazy() as agent:
                self.__transport = await agent.spawn(self.__my_verkey, self.__endpoint)
                await self.__transport.start(protocols=[], time_to_live=self.time_to_live)
                self.__is_start = True
        return self.__transport


class CoProtocolP2P(AbstractCoProtocol):

    def __init__(self, pairwise: Pairwise, time_to_live: int = None):
        super().__init__(time_to_live=time_to_live)
        self.__is_start = False
        self.__transport = None
        self.__pairwise = pairwise

    def __del__(self):
        if self.__is_start:
            asyncio.ensure_future(self.__transport.stop())

    async def send(self, message: Message):
        async with self.__get_transport_lazy() as transport:
            await transport.send(message)

    async def switch(self, message: Message) -> (bool, Message):
        async with self.__get_transport_lazy() as transport:
            success, response = await transport.switch(message)
        return success, response

    @asynccontextmanager
    async def __get_transport_lazy(self) -> PairwiseCoProtocolTransport:
        if self.__transport is None:
            async with _current_hub().get_agent_connection_lazy() as agent:
                self.__transport = await agent.spawn(self.__pairwise)
                await self.__transport.start(protocols=[], time_to_live=self.time_to_live)
                self.__is_start = True
        return self.__transport


class CoProtocolThreaded(AbstractCoProtocol):

    def __init__(self, thid: str, to: List[Pairwise], pthid: str = None, time_to_live: int = None):
        super().__init__(time_to_live=time_to_live)
        self.__is_start = False
        self.__thid = thid
        self.__pthid = pthid
        self.__transport = None
        self.__to = to

    def __del__(self):
        if self.__is_start:
            asyncio.ensure_future(self.__transport.stop())

    async def send(self, message: Message) -> List[Any]:
        async with self.__get_transport_lazy() as transport:
            ret = await transport.send_many(message, self.__to)
        return ret

    async def switch(self, message: Message) -> (bool, Message):
        pass

    @asynccontextmanager
    async def __get_transport_lazy(self) -> TheirEndpointCoProtocolTransport:
        if self.__transport is None:
            async with _current_hub().get_agent_connection_lazy() as agent:
                if self.__pthid is None:
                    self.__transport = await agent.spawn(self.__thid)
                else:
                    self.__transport = await agent.spawn(self.__thid, self.__pthid)
                await self.__transport.start(protocols=[], time_to_live=self.time_to_live)
                self.__is_start = True
        return self.__transport
