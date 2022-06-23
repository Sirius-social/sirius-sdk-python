from enum import Enum
from abc import ABC, abstractmethod
from typing import List, Union, Optional
from dataclasses import dataclass

import sirius_sdk
from .streams import AbstractReadOnlyStream, AbstractWriteOnlyStream, AbstractStreamEncryption
from .documents import EncryptedDocument


class StructuredDocument:
    """A structured document is used to store application data as well as metadata about the application data.
       This information is typically encrypted and then stored on the data vault.

    see details:  https://identity.foundation/confidential-storage/#structureddocument
    """

    def __init__(self, id_: str, meta: dict, content: Union[AbstractReadOnlyStream, EncryptedDocument]):
        self.__id = id_
        self.__meta = dict(**meta)
        if isinstance(content, AbstractReadOnlyStream):
            self.__meta['chunks'] = content.chunks_num
        self.__content = content

    @property
    def id(self) -> str:
        return self.__id

    @property
    def meta(self) -> dict:
        return self.__meta

    @property
    def content(self) -> Union[AbstractReadOnlyStream, EncryptedDocument]:
        return self.__content


class ConfidentialStorageAuthProvider:
    """Layer C: Authorization (policy enforcement point)

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    class PermissionLevel(Enum):
        # Entity may run read-operations
        CAN_READ = 'CAN_READ'
        # Entity has access to write/update document/streams
        CAN_WRITE = 'CAN_WRITE'
        # Entity can create new documents/streams
        CAN_CREATE = 'CAN_CREATE'

    def __init__(self):
        self.__entity = None

    @property
    def entity(self) -> Optional[sirius_sdk.Pairwise]:
        return self.__entity

    async def authorize(self, entity: sirius_sdk.Pairwise) -> bool:
        """Authorize participant

        In DESCENDANTS may invoke adv. proof verify procedures...

        :param entity: Service Client
        :return: success
        """
        self.__entity = entity
        return True

    def has_permissions(self) -> List[PermissionLevel]:
        """
        :return: list of DataVault permissions for client
        """
        return [
            self.PermissionLevel.CAN_READ,
            self.PermissionLevel.CAN_WRITE,
            self.PermissionLevel.CAN_CREATE
        ]

    def can_read(self) -> bool:
        return self.PermissionLevel.CAN_READ in self.has_permissions()

    def can_write(self) -> bool:
        return self.PermissionLevel.CAN_WRITE in self.has_permissions()

    def can_create(self) -> bool:
        return self.PermissionLevel.CAN_CREATE in self.has_permissions()


@dataclass
class VaultConfig:
    """Data vault configuration isn't strictly necessary for using the other features of data vaults.
    This should have its own conformance section/class or potentially event be non-normative.

    details: https://identity.foundation/confidential-storage/#datavaultconfiguration"""

    @dataclass
    class KeyAgreement:
        # An identifier for the key agreement key. The value is required and MUST be a URI.
        # The key agreement key is used to derive a secret that is then used
        # to generate a key encryption key for the receiver.
        id: str
        # The type of key agreement key. The value is required and MUST be or map to a URI.
        type: str

        @property
        def is_filled(self) -> bool:
            if self.id or self.type:
                return True
            else:
                return False

    @dataclass
    class HMAC:
        # An identifier for the HMAC key. The value is required a MUST be or map to a URI.
        id: str
        # The type of HMAC key. The value is required and MUST be or map to a URI.
        type: str

        @property
        def is_filled(self) -> bool:
            if self.id or self.type:
                return True
            else:
                return False

    # A unique counter for the data vault in order to ensure that clients are
    # properly synchronized to the data vault. Example: 0
    sequence: int
    # The entity or cryptographic key that is in control of the data vault.
    # The value is required and MUST be a URI. Example: "did:example:123456789"
    controller: str
    # The root entities or cryptographic key(s) that are authorized to invoke an authorization capability
    # to modify the data vault's configuration or read or write to it.
    # The value is optional, but if present, MUST be a URI or an array of URIs.
    # When this value is not present, the value of controller property is used for the same purpose.
    invoker: Optional[Union[str, List[str]]]
    # The root entities or cryptographic key(s) that are authorized to delegate authorization capabilities
    # to modify the data vault's configuration or read or write to it.
    # The value is optional, but if present, MUST be a URI or an array of URIs.
    # When this value is not present, the value of controller property is used for the same purpose.
    delegator: Optional[Union[str, List[str]]]
    # Used to express an application-specific reference identifier.
    # The value is optional and, if present, MUST be a string.
    reference_id: Optional[str]
    # keyAgreementKey
    key_agreement: Optional[KeyAgreement]
    # HMAC
    hmac: Optional[HMAC]

    def as_json(self) -> dict:
        js = {
            'sequence': self.sequence,
            'controller': self.controller,
        }
        if self.invoker:
            js['invoker'] = self.invoker
        if self.delegator:
            js['referenceId'] = self.reference_id
        if self.key_agreement and self.key_agreement.is_filled:
            js['keyAgreementKey'] = {
                'id': self.key_agreement.id,
                'type': self.key_agreement.type
            }
        if self.hmac and self.hmac.is_filled:
            js['hmac'] = {
                'id': self.hmac.id,
                'type': self.hmac.type
            }
        return js

    def from_json(self, js: dict):
        js = dict(**js)
        self.sequence = js.pop('sequence', 0)
        self.controller = js.pop('controller', None)
        self.invoker = js.pop('invoker', None)
        self.reference_id = js.pop('referenceId', None)
        key_agreement = js.pop('keyAgreementKey', {})
        key_agreement_id = key_agreement.get('id', None)
        key_agreement_type = key_agreement.get('type', None)
        if key_agreement_id or key_agreement_type:
            self.key_agreement = VaultConfig.KeyAgreement(
                key_agreement_id, key_agreement_type
            )
        else:
            self.key_agreement = None
        hmac = js.pop('hmac', {})
        hmac_id = hmac.get('id', None)
        hmac_type = hmac_id.get('type', None)
        if hmac_id or hmac_type:
            self.hmac = VaultConfig.HMAC(
                hmac_id, hmac_type
            )
        else:
            self.hmac = None
        # Copy others
        for fld, value in js.items():
            self.__setattr__(fld, value)


class EncryptedDataVault:
    """Layer B: Encrypted Vault Storage

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    def __init__(self, auth: ConfidentialStorageAuthProvider, cfg: VaultConfig):
        self.__auth = auth
        self.__cfg = cfg

    @property
    def auth(self) -> ConfidentialStorageAuthProvider:
        return self.__auth

    @property
    def cfg(self) -> VaultConfig:
        return self.__cfg

    class Indexes:
        async def apply(self, **filters) -> List[StructuredDocument]:
            pass


class ConfidentialStorageRawByteStorage(ABC):
    """Layer A: raw bytes storage (Cloud, DB, File-system, Mobile, etc)

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    def __init__(self, encryption: AbstractStreamEncryption = None):
        self.__encryption = encryption

    @property
    def encryption(self) -> Optional[AbstractStreamEncryption]:
        return self.__encryption

    @abstractmethod
    async def create(self, uri: str):
        raise NotImplementedError

    @abstractmethod
    async def remove(self, uri: str):
        raise NotImplementedError

    @abstractmethod
    async def readable(self, uri: str, chunks_num: int) -> AbstractReadOnlyStream:
        raise NotImplementedError

    @abstractmethod
    async def writeable(self, uri: str) -> AbstractWriteOnlyStream:
        raise NotImplementedError
