import asyncio
import threading
from typing import Optional
from contextlib import asynccontextmanager

from sirius_sdk.encryption.p2p import P2PConnection
from sirius_sdk.errors.exceptions import SiriusInitializationError
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.agent.wallet.abstract.crypto import AbstractCrypto
from sirius_sdk.agent.wallet.abstract.cache import AbstractCache
from sirius_sdk.agent.wallet.abstract.did import AbstractDID
from sirius_sdk.agent.wallet.abstract.anoncreds import AbstractAnonCreds
from sirius_sdk.agent.wallet.abstract.non_secrets import AbstractNonSecrets
from sirius_sdk.storages import AbstractImmutableCollection
from sirius_sdk.agent.microledgers.abstract import AbstractMicroledgerList
from sirius_sdk.agent.agent import Agent, BaseAgentConnection, SpawnStrategy
from .context import get as context_get, set as context_set, clear as context_clear


__ROOT_HUB = None
__THREAD_LOCAL_HUB = threading.local()


class Hub:

    def __init__(
            self, server_uri: str = None, credentials: bytes = None, p2p: P2PConnection = None, io_timeout: int = None,
            storage: AbstractImmutableCollection = None, crypto: AbstractCrypto = None,
            microledgers: AbstractMicroledgerList = None, pairwise_storage: AbstractPairwiseList = None,
            did: AbstractDID = None, anoncreds: AbstractAnonCreds = None, non_secrets: AbstractNonSecrets = None,
            cache: AbstractCache = None, loop: asyncio.AbstractEventLoop = None
    ):
        if server_uri or credentials or p2p:
            if server_uri and credentials and p2p:
                self.__allocate_agent = True
            else:
                raise RuntimeError('You must specify server_uri, credentials, p2p')
        else:
            self.__allocate_agent = False
        self.__crypto = crypto
        self.__microledgers = microledgers
        self.__pairwise_storage = pairwise_storage
        self.__did = did
        self.__anoncreds = anoncreds
        self.__non_secrets = non_secrets
        self.__cache = cache
        self.__server_uri = server_uri
        self.__credentials = credentials
        self.__p2p = p2p
        self.__timeout = io_timeout or BaseAgentConnection.IO_TIMEOUT
        self.__storage = storage
        self.__loop = loop or asyncio.get_event_loop()
        self.__create_agent_instance()

    def __del__(self):
        if self.__allocate_agent and self.__agent.is_open and self.__loop.is_running():
            asyncio.ensure_future(self.__agent.close(), loop=self.__loop)

    def copy(self):
        inst = Hub(
            server_uri=self.__server_uri, credentials=self.__credentials, p2p=self.__p2p
        )
        inst.__crypto = self.__crypto
        inst.__microledgers = self.__microledgers
        inst.__pairwise_storage = self.__pairwise_storage
        inst.__did = self.__did
        inst.__anoncreds = self.__anoncreds
        inst.__non_secrets = self.__non_secrets
        inst.__storage = self.__storage
        inst.__cache = self.__cache
        return inst

    async def abort(self):
        if not self.__allocate_agent:
            return
        if self.__loop.is_running():
            if self.__loop == asyncio.get_event_loop():
                old_agent = self.__agent
                self.__create_agent_instance()
                if old_agent.is_open:
                    await old_agent.close()
            else:
                asyncio.ensure_future(self.abort(), loop=self.__loop)

    def run_soon(self, coro):
        assert asyncio.iscoroutine(coro), 'Expected coroutine object'
        if self.__loop.is_running():
            asyncio.ensure_future(coro, loop=self.__loop)

    @asynccontextmanager
    async def get_agent_connection_lazy(self):
        if not self.__allocate_agent:
            yield None
        if not self.__agent.is_open:
            await self.__agent.open()
        yield self.__agent

    async def open(self):
        if not self.__allocate_agent:
            return
        async with self.get_agent_connection_lazy() as agent:
            pass

    async def close(self):
        if not self.__allocate_agent:
            return
        if self.__agent.is_open:
            await self.__agent.close()

    async def get_crypto(self) -> AbstractCrypto:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__crypto or agent.wallet.crypto
        else:
            return self.__crypto

    async def get_microledgers(self) -> AbstractMicroledgerList:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__microledgers or agent.microledgers
        else:
            return self.__microledgers

    async def get_pairwise_list(self) -> AbstractPairwiseList:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__pairwise_storage or agent.pairwise_list
        else:
            return self.__pairwise_storage

    async def get_did(self) -> AbstractDID:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__did or agent.wallet.did
        else:
            return self.__did

    async def get_anoncreds(self) -> AbstractAnonCreds:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__anoncreds or agent.wallet.anoncreds
        else:
            return self.__anoncreds

    async def get_cache(self) -> AbstractCache:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__cache or agent.wallet.cache
        else:
            return self.__cache

    async def get_non_secrets(self) -> AbstractNonSecrets:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__non_secrets or agent.wallet.non_secrets
        else:
            return self.__non_secrets

    def __create_agent_instance(self):
        if self.__allocate_agent:
            self.__agent = Agent(
                server_address=self.__server_uri,
                credentials=self.__credentials,
                p2p=self.__p2p,
                timeout=self.__timeout,
                loop=self.__loop,
                storage=self.__storage,
                spawn_strategy=SpawnStrategy.CONCURRENT
            )


def init(server_uri: str = None, credentials: bytes = None, p2p: P2PConnection = None, io_timeout: int = None,
         storage: AbstractImmutableCollection = None,
         crypto: AbstractCrypto = None, microledgers: AbstractMicroledgerList = None,
         did: AbstractDID = None, pairwise_storage: AbstractPairwiseList = None, non_secrets: AbstractNonSecrets = None
         ):
    global __ROOT_HUB
    root = Hub(
        server_uri=server_uri, credentials=credentials, p2p=p2p, io_timeout=io_timeout,
        storage=storage, crypto=crypto, microledgers=microledgers,
        pairwise_storage=pairwise_storage, did=did, non_secrets=non_secrets
    )
    loop = asyncio.get_event_loop()
    if loop.is_running():
        raise SiriusInitializationError('You must call this method outside coroutine')
    loop.run_until_complete(root.open())
    __ROOT_HUB = root


@asynccontextmanager
async def context(
          server_uri: str = None, credentials: bytes = None, p2p: P2PConnection = None, io_timeout: int = None,
          storage: AbstractImmutableCollection = None,
          crypto: AbstractCrypto = None, microledgers: AbstractMicroledgerList = None,
          did: AbstractDID = None, pairwise_storage: AbstractPairwiseList = None,
          non_secrets: AbstractNonSecrets = None
):
    hub = Hub(
        server_uri=server_uri, credentials=credentials, p2p=p2p, io_timeout=io_timeout,
        storage=storage, crypto=crypto, microledgers=microledgers,
        pairwise_storage=pairwise_storage, did=did, non_secrets=non_secrets
    )
    old_hub = __get_thread_local_gub()
    __THREAD_LOCAL_HUB.instance = hub
    try:
        await hub.open()
        old_hub_coro = context_get('hub')
        context_set('hub', hub)
        try:
            yield
        finally:
            context_clear()
            await hub.close()
            context_set('hub', old_hub_coro)
    finally:
        __THREAD_LOCAL_HUB.instance = old_hub


def __get_root_hub() -> Optional[Hub]:
    return __ROOT_HUB


def __get_thread_local_gub() -> Optional[Hub]:
    # For now thread local context not used but code prepared for future purposes
    try:
        inst = __THREAD_LOCAL_HUB.instance
    except AttributeError:
        inst = None
    return inst


def _current_hub() -> Hub:
    inst = context_get('hub')
    if inst is None:
        root_hub = __get_thread_local_gub() or __get_root_hub()
        if root_hub is None:
            raise SiriusInitializationError('Non initialized Sirius Agent connection')
        inst = root_hub.copy()
        context_set('hub', inst)
    return inst
