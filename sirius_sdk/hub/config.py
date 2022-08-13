from dataclasses import dataclass
from typing import Union, Dict, Any, Optional

from sirius_sdk.encryption.p2p import P2PConnection
from sirius_sdk.errors.exceptions import SiriusInitializationError
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.abstract.api import APICrypto, APITransport, APIContents, APIDistributedLocks, \
    APICoProtocols, APIRouter, APINetworks
from sirius_sdk.agent.wallet.abstract.did import AbstractDID
from sirius_sdk.agent.wallet.abstract.anoncreds import AbstractAnonCreds
from sirius_sdk.agent.wallet.abstract.cache import AbstractCache
from sirius_sdk.agent.wallet.abstract.non_secrets import AbstractNonSecrets
from sirius_sdk.abstract.storage import AbstractKeyValueStorage
from sirius_sdk.agent.microledgers.abstract import AbstractMicroledgerList


class Config:

    @dataclass
    class Overrides:
        crypto: APICrypto = None
        did: AbstractDID = None
        microledgers: AbstractMicroledgerList = None
        storage: AbstractKeyValueStorage = None
        pairwise_storage: AbstractPairwiseList = None
        non_secrets: AbstractNonSecrets = None
        anoncreds: AbstractAnonCreds = None
        cache: AbstractCache = None
        coprotocols: APICoProtocols = None
        transport: APITransport = None
        contents: APIContents = None
        distr_locks: APIDistributedLocks = None
        router: APIRouter = None
        networks: APINetworks = None

    @dataclass
    class CloudOpts:
        server_uri: str = None
        credentials: Union[str, bytes] = None
        p2p: P2PConnection = None
        io_timeout: int = None

        @property
        def is_filled(self) -> bool:
            return self.server_uri is not None and self.credentials is not None and self.p2p is not None

    @dataclass
    class MediatorOpts:
        uri: str = None
        my_verkey: str = None
        mediator_verkey: str = None

        @property
        def is_filled(self) -> bool:
            return self.uri is not None and self.my_verkey is not None and self.mediator_verkey is not None

    def __init__(self):
        self.__overrides = self.Overrides()
        self.__cloud_opts = self.CloudOpts()
        self.__mediator_opts = self.MediatorOpts()

    @property
    def overrides(self) -> Overrides:
        return self.__overrides

    @property
    def cloud_opts(self) -> CloudOpts:
        return self.__cloud_opts

    @property
    def mediator_opts(self) -> MediatorOpts:
        return self.__mediator_opts

    def setup_cloud(
            self, *args, server_uri: str = None, credentials: Union[bytes, str] = None,
            p2p: Union[P2PConnection, dict] = None, io_timeout: int = None
    ) -> "Config":
        if args:
            if len(args) == 3:
                return self.setup_cloud(server_uri=args[0], credentials=args[1], p2p=args[2])
            else:
                cfg = args[0]
                if type(cfg) is dict:
                    return self.setup_cloud(**cfg)
                else:
                    raise SiriusInitializationError('Expected configuration as dictionary of params')
        # setup cloud agent connection url
        if server_uri is None:
            raise SiriusInitializationError('"server_uri" must be set')
        self.__cloud_opts.server_uri = server_uri
        # setup credentials
        if credentials is None:
            raise SiriusInitializationError('"credentials" must be set')
        elif type(credentials) is str:
            self.__cloud_opts.credentials = credentials.encode()
        elif type(credentials) is bytes:
            self.__cloud_opts.credentials = credentials
        else:
            raise SiriusInitializationError('Unexpected credentials type. Expected str or bytes')
        # setup p2p connection
        if p2p is None:
            raise SiriusInitializationError('"p2p" must be set')
        if type(p2p) is dict:
            their_verkey = p2p.get('their_verkey', None)
            if their_verkey is None:
                raise SiriusInitializationError('p2p does not have "their_verkey" attribute')
            if type(their_verkey) is not str:
                raise SiriusInitializationError('p2p "their_verkey" attribute is not base58 string')
            my_keys = p2p.get('my_keys', None)
            if my_keys is None:
                raise SiriusInitializationError('p2p does not have "my_keys" attribute')
            if type(my_keys) is not list:
                raise SiriusInitializationError('p2p "my_keys" attribute is not base58 keys list')
            if len(my_keys) != 2:
                raise SiriusInitializationError('p2p "my_keys" attribute unexpected structure')
            self.__cloud_opts.p2p = P2PConnection(my_keys=tuple(my_keys), their_verkey=their_verkey)
        elif type(p2p) is P2PConnection:
            self.__cloud_opts.p2p = p2p
        else:
            raise SiriusInitializationError('Unexpected p2p type')
        if io_timeout:
            self.__cloud_opts.io_timeout = io_timeout
        return self

    def setup_mediator(self, uri: str, my_verkey: str, mediator_verkey: str) -> "Config":
        self.__mediator_opts = self.MediatorOpts(uri=uri, my_verkey=my_verkey, mediator_verkey=mediator_verkey)
        return self

    def override(
            self, crypto: APICrypto = None, did: AbstractDID = None,
            microledgers: AbstractMicroledgerList = None, storage: AbstractKeyValueStorage = None,
            pairwise_storage: AbstractPairwiseList = None, non_secrets: AbstractNonSecrets = None,
            anon_cred: AbstractAnonCreds = None, coprotocols: APICoProtocols = None, router: APIRouter = None,
            transport: APITransport = None, contents: APIContents = None,
            distr_locks: APIDistributedLocks = None, networks: APINetworks = None, **kwargs
    ) -> "Config":
        if crypto:
            self.__overrides.crypto = crypto
        if did:
            self.__overrides.did = did
        if microledgers:
            self.__overrides.microledgers = microledgers
        if storage:
            self.__overrides.storage = storage
        if pairwise_storage:
            self.__overrides.pairwise_storage = pairwise_storage
        if non_secrets:
            self.__overrides.non_secrets = non_secrets
        if anon_cred:
            self.__overrides.anon_cred = anon_cred
        if coprotocols:
            self.__overrides.coprotocols = coprotocols
        if transport:
            self.__overrides.transport = transport
        if contents:
            self.__overrides.contents = contents
        if distr_locks:
            self.__overrides.distr_locks = distr_locks
        if router:
            self.__overrides.router = router
        if networks:
            self.__overrides.networks = networks
        return self

    def override_crypto(self, dependency: APICrypto) -> "Config":
        self.__overrides.crypto = dependency
        return self

    def override_did(self, dependency: AbstractDID) -> "Config":
        self.__overrides.did = dependency
        return self

    def override_microledgers(self, dependency: AbstractMicroledgerList) -> "Config":
        self.__overrides.microledgers = dependency
        return self

    def override_storage(self, dependency: AbstractKeyValueStorage) -> "Config":
        self.__overrides.storage = dependency
        return self

    def override_pairwise_storage(self, dependency: AbstractPairwiseList) -> "Config":
        self.__overrides.pairwise_storage = dependency
        return self

    def override_non_secrets(self, dependency: AbstractNonSecrets) -> "Config":
        self.__overrides.non_secrets = dependency
        return self

    def override_anon_cred(self, dependency: AbstractAnonCreds) -> "Config":
        self.__overrides.anon_cred = dependency
        return self

    def override_coprotocols(self, dependency: APICoProtocols) -> "Config":
        self.__overrides.coprotocols = dependency
        return self

    def override_transport(self, dependency: APITransport) -> "Config":
        self.__overrides.transport = dependency
        return self

    def override_contents(self, dependency: APIContents) -> "Config":
        self.__overrides.contents = dependency
        return self

    def override_distr_locks(self, dependency: APIDistributedLocks) -> "Config":
        self.__overrides.distr_locks = dependency
        return self

    def override_router(self, dependency: APIRouter) -> "Config":
        self.__overrides.router = dependency
        return self

    def override_networks(self, dependency: APINetworks) -> "Config":
        self.__overrides.networks = dependency
        return self
