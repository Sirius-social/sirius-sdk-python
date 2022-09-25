import asyncio
import hashlib
import json
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
from sirius_sdk.abstract.storage import AbstractKeyValueStorage
from sirius_sdk.agent.microledgers.abstract import AbstractMicroledgerList
from sirius_sdk.agent.agent import Agent, SpawnStrategy

from .defaults.default_apis import APIDefault
from .defaults.default_crypto import DefaultCryptoService as DefaultCryptoService
from .defaults.default_storage import InMemoryKeyValueStorage
from .defaults.default_non_secrets import DefaultNonSecretsStorage
from .context import get as context_get, set as context_set, clear as context_clear
from .config import Config
from .mediator import Mediator
from .backgrounds import BackgroundScheduler

__ROOT_HUB = None
__THREAD_LOCAL_HUB = threading.local()


class Hub:

    def __init__(self, config: Config, loop: asyncio.AbstractEventLoop = None):

        self.__config: Config = config
        self.__loop = loop or asyncio.get_event_loop()
        self.__agent: Optional[Agent] = None
        self.__allocate_agent = False
        self.__mediator: Optional[Mediator] = None
        self.__allocate_mediator = False

        self.__storage: Optional[AbstractKeyValueStorage] = config.overrides.storage
        if self.__storage is None and not config.cloud_opts.is_filled:
            logging.warning(
                'Storage will be set to InMemory-Storage as default, it will outcome issues in production environments'
            )
            self.__storage = InMemoryKeyValueStorage()

        # Check if configured as cloud-agent
        if config.cloud_opts.is_filled:
            self.__allocate_agent = True
            self.__create_agent_instance(external_crypto=config.overrides.crypto)
        elif config.mediator_opts.is_filled:
            self.__allocate_mediator = True
            self.__create_mediator_instance(pairwise_resolver=config.overrides.pairwise_storage)
        else:
            logging.warning('You should configure cloud-agent or mediator options')
        # Crypto and default services
        self.__crypto: Optional[APICrypto] = config.overrides.crypto
        self.__default_api: APIDefault = APIDefault()
        self.__default_crypto: APICrypto = DefaultCryptoService(storage=self.__storage)
        self.__default_non_secrets = DefaultNonSecretsStorage(storage=self.__storage)

    def __del__(self):
        if self.__loop and self.__loop.is_running():
            if self.__agent is not None and self.__agent.is_open:
                asyncio.ensure_future(self.__agent.close(), loop=self.__loop)
            if self.__mediator is not None and self.__mediator.is_connected:
                asyncio.ensure_future(self.__mediator.disconnect(), loop=self.__loop)

    @property
    def global_id(self) -> Optional[str]:
        if self.__config.cloud_opts.is_filled:
            if isinstance(self.__config.cloud_opts.credentials, str):
                cred = self.__config.cloud_opts.credentials.encode()
            else:
                cred = self.__config.cloud_opts.credentials
            return hashlib.md5(cred).hexdigest()
        elif self.__config.mediator_opts.is_filled:
            cred = f'{self.__config.mediator_opts.my_verkey}:{self.__config.mediator_opts.mediator_verkey}'
            return hashlib.md5(cred).hexdigest()
        else:
            return None

    def copy(self):
        inst = Hub(config=self.__config)
        return inst

    async def abort(self):
        if not self.__allocate_agent:
            return
        if self.__loop.is_running():
            if self.__loop == asyncio.get_event_loop():
                old_agent = self.__agent
                self.__create_agent_instance(external_crypto=self.__config.overrides.crypto)
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
        if self.__allocate_agent:
            if not self.__agent.is_open:
                await self.__agent.open()
            yield self.__agent
        elif self.__allocate_mediator:
            if not self.__mediator.is_connected:
                await self.__mediator.connect()
            yield self.__mediator
        else:
            yield None

    async def open(self):
        if not (self.__allocate_agent or self.__allocate_mediator):
            return
        async with self.get_agent_connection_lazy():
            pass

    async def close(self):
        if self.__allocate_agent and self.__agent and self.__agent.is_open:
            await self.__agent.close()
        if self.__allocate_mediator and self.__mediator and self.__mediator.is_connected:
            await self.__mediator.disconnect()

    async def get_crypto(self) -> APICrypto:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__crypto or agent.wallet.crypto or self.__default_crypto
        else:
            return self.__crypto or self.__default_crypto

    async def get_microledgers(self) -> Optional[AbstractMicroledgerList]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__config.overrides.microledgers or agent.microledgers
        else:
            return self.__config.overrides.microledgers

    async def get_pairwise_list(self) -> Optional[AbstractPairwiseList]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__config.overrides.pairwise_storage or agent.pairwise_list
        else:
            return self.__config.overrides.pairwise_storage

    async def get_did(self) -> Optional[AbstractDID]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__config.overrides.did or agent.wallet.did
        else:
            return self.__config.overrides.did

    async def get_anoncreds(self) -> Optional[AbstractAnonCreds]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__config.overrides.anoncreds or agent.wallet.anoncreds
        else:
            return self.__config.overrides.anoncreds

    async def get_cache(self) -> Optional[AbstractCache]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__config.overrides.cache or agent.wallet.cache
        else:
            return self.__config.overrides.cache

    async def get_non_secrets(self) -> Optional[AbstractNonSecrets]:
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                return self.__config.overrides.non_secrets or agent.wallet.non_secrets
        else:
            return self.__config.overrides.non_secrets or self.__default_non_secrets

    async def get_coprotocols(self) -> Optional[APICoProtocols]:
        api: Optional[APICoProtocols] = None
        if self.__allocate_agent or self.__allocate_mediator:
            async with self.get_agent_connection_lazy() as conn:
                if isinstance(conn, APICoProtocols):
                    api = conn
        return self.__config.overrides.coprotocols or api or self.__default_api

    async def get_transport(self) -> Optional[APITransport]:
        api: Optional[APITransport] = None
        if self.__allocate_agent or self.__allocate_mediator:
            async with self.get_agent_connection_lazy() as conn:
                if isinstance(conn, APITransport):
                    api = conn
        return self.__config.overrides.coprotocols or api or self.__default_api

    async def get_contents(self) -> Optional[APIContents]:
        api: Optional[APIContents] = None
        if self.__allocate_agent or self.__allocate_mediator:
            async with self.get_agent_connection_lazy() as conn:
                if isinstance(conn, APIContents):
                    api = conn
        return self.__config.overrides.contents or api or self.__default_api

    async def get_distr_locks(self) -> Optional[APIDistributedLocks]:
        api: Optional[APIDistributedLocks] = None
        if self.__allocate_agent or self.__allocate_mediator:
            async with self.get_agent_connection_lazy() as conn:
                if isinstance(conn, APIDistributedLocks):
                    api = conn
        return self.__config.overrides.distr_locks or api or self.__default_api

    async def get_router(self) -> Optional[APIRouter]:
        api: Optional[APIRouter] = None
        if self.__allocate_agent or self.__allocate_mediator:
            async with self.get_agent_connection_lazy() as conn:
                if isinstance(conn, APIRouter):
                    api = conn
        return self.__config.overrides.router or api

    async def get_networks(self) -> Optional[APINetworks]:
        api: Optional[APINetworks] = None
        if self.__allocate_agent or self.__allocate_mediator:
            async with self.get_agent_connection_lazy() as conn:
                if isinstance(conn, APINetworks):
                    api = conn
        return self.__config.overrides.networks or api

    async def ping(self) -> bool:
        success = False
        if self.__allocate_agent:
            async with self.get_agent_connection_lazy() as agent:
                if isinstance(agent, Agent):
                    success = await agent.ping()
                elif isinstance(agent, Mediator):
                    success = agent.is_connected
        return success

    def __create_agent_instance(self, external_crypto: APICrypto):
        if self.__allocate_agent:
            self.__agent = Agent(
                server_address=self.__config.cloud_opts.server_uri,
                credentials=self.__config.cloud_opts.credentials,
                p2p=self.__config.cloud_opts.p2p,
                timeout=self.__config.cloud_opts.io_timeout,
                loop=self.__loop,
                storage=None,
                spawn_strategy=SpawnStrategy.CONCURRENT,
                external_crypto=external_crypto
            )

    def __create_mediator_instance(self, pairwise_resolver: AbstractPairwiseList = None):
        if self.__allocate_mediator:
            self.__mediator = Mediator(
                uri=self.__config.mediator_opts.uri,
                my_verkey=self.__config.mediator_opts.my_verkey,
                mediator_verkey=self.__config.mediator_opts.mediator_verkey,
                pairwise_resolver=pairwise_resolver
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
        old_hub_coro = context_get('hub')
        context_set('hub', hub)
        await hub.open()
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
