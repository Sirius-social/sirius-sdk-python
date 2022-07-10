import asyncio
import logging
import warnings
import threading
from typing import Optional
from contextlib import asynccontextmanager

from sirius_sdk.errors.exceptions import SiriusInitializationError
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.abstract.api import APICrypto, APICoProtocols, APITransport, APIContents, APIDistributedLocks,\
    APIRouter, APINetworks
from sirius_sdk.agent.wallet.abstract.cache import AbstractCache
from sirius_sdk.agent.wallet.abstract.did import AbstractDID
from sirius_sdk.agent.wallet.abstract.anoncreds import AbstractAnonCreds
from sirius_sdk.agent.wallet.abstract.non_secrets import AbstractNonSecrets
from sirius_sdk.storages import AbstractImmutableCollection
from sirius_sdk.agent.microledgers.abstract import AbstractMicroledgerList
from sirius_sdk.agent.agent import Agent, SpawnStrategy
from sirius_sdk.abstract.bus import AbstractBus

from .defaults.default_apis import APIDefault
from .defaults.inmemory_crypto import InMemoryCrypto as DefaultCryptoService
from .context import get as context_get, set as context_set, clear as context_clear
from .config import Config


__ROOT_HUB = None
__THREAD_LOCAL_HUB = threading.local()


class Hub:

    def __init__(self, config: Config, loop: asyncio.AbstractEventLoop = None):
        self.__config: Config = config
        self.__storage: Optional[AbstractImmutableCollection] = config.overrides.storage
        self.__loop = loop or asyncio.get_event_loop()
        self.__agent: Optional[Agent] = None
        # Crypto
        self.__crypto: Optional[APICrypto] = config.overrides.crypto
        # Check if configured as cloud-agent
        if config.cloud_opts.is_filled:
            self.__allocate_agent = True
            self.__create_agent_instance(external_crypto=self.__crypto)
        elif config.mediator_opts.is_filled:
            pass
            # TODO
        else:
            logging.warning('You should configure cloud-agent or mediator options')
            self.__allocate_agent = False
        self.__default_api: APIDefault = APIDefault(self.__crypto)
        self.__default_crypto: APICrypto = DefaultCryptoService()
        # Microledgers and other services
        self.__microledgers = config.overrides.microledgers
        self.__pairwise_storage = config.overrides.pairwise_storage
        self.__did = config.overrides.did
        self.__anoncreds = config.overrides.anoncreds
        self.__non_secrets = config.overrides.non_secrets
        self.__cache = config.overrides.cache
        self.__contents: Optional[APIContents] = config.overrides.contents
        self.__transport: Optional[APITransport] = config.overrides.coprotocols
        self.__coprotocols: Optional[AbstractBus] = config.overrides.coprotocols
        self.__distr_locks: Optional[APIDistributedLocks] = config.overrides.distr_locks
        self.__router: Optional[APIRouter] = config.overrides.router
        self.__networks: Optional[APINetworks] = config.overrides.networks

    def __del__(self):
        if self.__allocate_agent and self.__agent.is_open and self.__loop.is_running():
            asyncio.ensure_future(self.__agent.close(), loop=self.__loop)

    def copy(self):
        inst = Hub(config=self.__config)
        return inst

    async def abort(self):
        if not self.__allocate_agent:
            return
        if self.__loop.is_running():
            if self.__loop == asyncio.get_event_loop():
                old_agent = self.__agent
                self.__create_agent_instance(external_crypto=self.__crypto)
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

    async def get_crypto(self) -> APICrypto:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__crypto or agent.wallet.crypto or self.__default_crypto
        else:
            return self.__crypto or self.__default_crypto

    async def get_microledgers(self) -> Optional[AbstractMicroledgerList]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__microledgers or agent.microledgers
        else:
            return self.__microledgers

    async def get_pairwise_list(self) -> Optional[AbstractPairwiseList]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__pairwise_storage or agent.pairwise_list
        else:
            return self.__pairwise_storage

    async def get_did(self) -> Optional[AbstractDID]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__did or agent.wallet.did
        else:
            return self.__did

    async def get_anoncreds(self) -> Optional[AbstractAnonCreds]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__anoncreds or agent.wallet.anoncreds
        else:
            return self.__anoncreds

    async def get_cache(self) -> Optional[AbstractCache]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__cache or agent.wallet.cache
        else:
            return self.__cache

    async def get_non_secrets(self) -> Optional[AbstractNonSecrets]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__non_secrets or agent.wallet.non_secrets
        else:
            return self.__non_secrets

    async def get_coprotocols(self) -> Optional[APICoProtocols]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__coprotocols or agent
        return self.__coprotocols or self.__default_api

    async def get_transport(self) -> Optional[APITransport]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__transport or agent
        return self.__transport or self.__default_api

    async def get_contents(self) -> Optional[APIContents]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__contents or agent
        return self.__contents or self.__default_api

    async def get_distr_locks(self) -> Optional[APIDistributedLocks]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__distr_locks or agent
        return self.__distr_locks or self.__default_api

    async def get_router(self) -> Optional[APIRouter]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__router or agent
        return self.__router

    async def get_networks(self) -> Optional[APINetworks]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__networks or agent
        return self.__networks

    async def ping(self) -> bool:
        success = False
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                success = await agent.ping()
        return success

    def __create_agent_instance(self, external_crypto: APICrypto):
        if self.__allocate_agent:
            self.__agent = Agent(
                server_address=self.__config.cloud_opts.server_uri,
                credentials=self.__config.cloud_opts.credentials,
                p2p=self.__config.cloud_opts.p2p,
                timeout=self.__config.cloud_opts.io_timeout,
                loop=self.__loop,
                storage=self.__storage,
                spawn_strategy=SpawnStrategy.CONCURRENT,
                external_crypto=external_crypto
            )


def __restore_config_from_kwargs(*args, **kwargs) -> Config:
    if args:
        first_arg = args[0]
        if type(first_arg) is not Config:
            warnings.warn('Use sirius_sdk.Config to configure SDK', DeprecationWarning)
    if kwargs:
        for arg in kwargs.keys():
            warnings.warn(f'{arg} param is Deprecated. Use sirius_sdk.Config to configure SDK', DeprecationWarning)
    if args:
        first = args[0]
        if type(first) is Config:
            cfg = first
        else:
            cfg = Config()
        if len(args) >= 3:
            opts = list(args)[:3]
            cfg.setup_cloud(*opts)
    else:
        cfg = Config()

    server_uri = kwargs.pop('server_uri', None) or kwargs.pop('server_address', None)
    credentials = kwargs.pop('credentials', None)
    p2p = kwargs.pop('p2p', None)
    io_timeout = kwargs.pop('io_timeout', None)
    if server_uri and credentials and p2p:
        cfg.setup_cloud(server_uri=server_uri, credentials=credentials, p2p=p2p, io_timeout=io_timeout)

    cfg.override(**kwargs)
    return cfg


def init(cfg: Config = None, *args, **kwargs):

    if cfg is not None and not isinstance(cfg, Config):
        first_arg = cfg
        cfg = None
        args = tuple([first_arg] + list(args))
    if cfg is None:
        warnings.warn('Use sirius_sdk.Config to configure SDK', DeprecationWarning)
        cfg = __restore_config_from_kwargs(*args, **kwargs)

    global __ROOT_HUB
    root = Hub(cfg)
    loop = asyncio.get_event_loop()
    if loop.is_running():
        raise SiriusInitializationError('You must call this method outside coroutine')
    loop.run_until_complete(root.open())
    __ROOT_HUB = root


@asynccontextmanager
async def context(cfg: Config = None, *args, **kwargs):

    if cfg is not None and not isinstance(cfg, Config):
        first_arg = cfg
        cfg = None
        args = tuple([first_arg] + list(args))
    if cfg is None:
        warnings.warn('Use sirius_sdk.Config to configure SDK', DeprecationWarning)
        cfg = __restore_config_from_kwargs(*args, **kwargs)

    hub = Hub(cfg)
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
