from typing import Union, Dict, Any, Optional

from sirius_sdk.encryption.p2p import P2PConnection
from sirius_sdk.errors.exceptions import SiriusInitializationError
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.agent.wallet.abstract.crypto import AbstractCrypto
from sirius_sdk.agent.wallet.abstract.did import AbstractDID
from sirius_sdk.agent.wallet.abstract.anoncreds import AbstractAnonCreds
from sirius_sdk.agent.wallet.abstract.non_secrets import AbstractNonSecrets
from sirius_sdk.storages import AbstractImmutableCollection
from sirius_sdk.agent.microledgers.abstract import AbstractMicroledgerList


class Config:

    def __init__(self):
        self.__overrides = {}
        self.__cloud_opts = {}
        self.__mediator_opts = {}

    @property
    def overrides(self) -> Dict[str, Any]:
        return self.__overrides

    @property
    def cloud_opts(self) -> Dict[str, Any]:
        return self.__cloud_opts

    @property
    def mediator_opts(self) -> Dict[str, Any]:
        return self.__mediator_opts

    def setup_cloud(
            self, server_uri: str, credentials: Union[bytes, str],
            p2p: Union[P2PConnection, dict], io_timeout: int = None
    ) -> "Config":
        # setup cloud agent connection url
        self.__cloud_opts = {'server_uri': server_uri}
        # setup credentials
        if type(credentials) is str:
            self.__cloud_opts['credentials'] = credentials.encode()
        elif type(credentials) is bytes:
            self.__cloud_opts['credentials'] = credentials
        else:
            raise SiriusInitializationError('Unexpected credentials type. Expected str or bytes')
        # setup p2p connection
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
            self.__cloud_opts['p2p'] = P2PConnection(my_keys=tuple(my_keys), their_verkey=their_verkey)
        elif type(p2p) is P2PConnection:
            self.__cloud_opts['p2p'] = p2p
        else:
            raise SiriusInitializationError('Unexpected p2p type')
        if io_timeout:
            self.__cloud_opts['io_timeout'] = io_timeout
        return self

    def setup_mediator(self, uri: str, my_verkey: str, mediator_verkey: str) -> "Config":
        self.__mediator_opts = {'uri': uri, 'my_verkey': my_verkey, 'mediator_verkey': mediator_verkey}
        return self

    def override(
            self, crypto: AbstractCrypto = None, did: AbstractDID = None,
            microledgers: AbstractMicroledgerList = None, storage: AbstractImmutableCollection = None,
            pairwise_storage: AbstractPairwiseList = None, non_secrets: AbstractNonSecrets = None,
            anon_cred: AbstractAnonCreds = None
    ) -> "Config":
        if crypto:
            self.__overrides['crypto'] = crypto
        if did:
            self.__overrides['did'] = did
        if microledgers:
            self.__overrides['microledgers'] = microledgers
        if storage:
            self.__overrides['storage'] = storage
        if pairwise_storage:
            self.__overrides['pairwise_storage'] = pairwise_storage
        if non_secrets:
            self.__overrides['non_secrets'] = non_secrets
        if anon_cred:
            self.__overrides['anon_cred'] = anon_cred
        return self

    def override_crypto(self, dependency: AbstractCrypto) -> "Config":
        self.__overrides['crypto'] = dependency
        return self

    def override_did(self, dependency: AbstractDID) -> "Config":
        self.__overrides['did'] = dependency
        return self

    def override_microledgers(self, dependency: AbstractMicroledgerList) -> "Config":
        self.__overrides['microledgers'] = dependency
        return self

    def override_storage(self, dependency: AbstractImmutableCollection) -> "Config":
        self.__overrides['storage'] = dependency
        return self

    def override_pairwise_storage(self, dependency: AbstractPairwiseList) -> "Config":
        self.__overrides['pairwise_storage'] = dependency
        return self

    def override_non_secrets(self, dependency: AbstractNonSecrets) -> "Config":
        self.__overrides['non_secrets'] = dependency
        return self

    def override_anon_cred(self, dependency: AbstractAnonCreds) -> "Config":
        self.__overrides['anon_cred'] = dependency
        return self
