import datetime
from enum import Enum
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import List, Union, Optional, Set

from sirius_sdk.abstract.p2p import Pairwise
from sirius_sdk.encryption.ed25519 import ensure_is_bytes
from .streams import AbstractReadOnlyStream, AbstractWriteOnlyStream, BaseStreamEncryption, \
    ReadOnlyStreamDecodingWrapper, WriteOnlyStreamEncodingWrapper, StreamEncryption, StreamDecryption
from .documents import EncryptedDocument
from .errors import ConfidentialStoragePermissionDenied
from .encoding import JWE, KeyPair
from .utils import datetime_to_utc_str


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

    def as_json(self) -> dict:
        return {'id': self.id, 'type': self.type}


class DocumentMeta(dict):

    def __init__(self, created: Union[str, datetime.datetime] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if created is not None:
            if isinstance(created, datetime.datetime):
                self['created'] = datetime_to_utc_str(created)
            else:
                self['created'] = created


class StreamMeta(DocumentMeta):

    def __init__(
            self, created: Union[str, datetime.datetime] = None,
            chunks: int = None,
            content_type: str = None,  # "video/mpeg", "image/png"
            *args, **kwargs
    ):
        super().__init__(created, *args, **kwargs)
        if chunks is not None:
            self['chunks'] = chunks
        if content_type is not None:
            self['contentType'] = content_type


class DataVaultStreamWrapper:

    def __init__(self, readable: AbstractReadOnlyStream = None, writable: AbstractWriteOnlyStream = None):
        self._readable = readable
        self._writable = writable

    async def readable(self, jwe: Union[JWE, dict] = None, keys: KeyPair = None) -> AbstractReadOnlyStream:
        if jwe is None:
            return self._readable
        else:
            enc = StreamDecryption.from_jwe(jwe)
            if keys is not None:
                enc.setup(vk=keys.pk, sk=keys.sk)
            return ReadOnlyStreamDecodingWrapper(src=self._readable, enc=enc)

    async def writable(self, jwe: Union[JWE, dict] = None, cek: Union[bytes, str] = None) -> AbstractWriteOnlyStream:
        if jwe is None:
            return self._writable
        else:
            if isinstance(cek, str):
                cek = ensure_is_bytes(cek)
            return WriteOnlyStreamEncodingWrapper(dest=self._writable, enc=StreamEncryption.from_jwe(jwe, cek))


class StructuredDocument:
    """A structured document is used to store application data as well as metadata about the application data.
       This information is typically encrypted and then stored on the data vault.

    see details:  https://identity.foundation/confidential-storage/#structureddocument
    """
    @dataclass
    class Index:
        sequence: int = None
        hmac: HMAC = None
        attributes: List[str] = None

    def __init__(
            self, id_: str, meta: dict,
            urn: str = None, indexed: List[Index] = None,
            content: EncryptedDocument = None,
            stream: DataVaultStreamWrapper = None
    ):
        self.__id = id_
        self.__meta = dict(**meta)
        self.__urn = urn
        if isinstance(content, AbstractReadOnlyStream):
            self.__meta['chunks'] = content.chunks_num
        self.__content = content
        self.__stream = stream
        self.__indexed: List[StructuredDocument.Index] = indexed or []

    @property
    def id(self) -> str:
        return self.__id

    @property
    def urn(self) -> str:
        return self.__urn or 'urn:id:' + self.__id

    @property
    def meta(self) -> dict:
        return self.__meta

    @property
    def content(self) -> Optional[EncryptedDocument]:
        return self.__content

    @property
    def doc(self) -> Optional[EncryptedDocument]:
        return self.__content

    @doc.setter
    def doc(self, value: Optional[EncryptedDocument]):
        self.__content = value

    @property
    def stream(self) -> Optional[DataVaultStreamWrapper]:
        return self.__stream

    @stream.setter
    def stream(self, value: Optional[DataVaultStreamWrapper]):
        self.__stream = value

    @property
    def indexed(self) -> List['Index']:
        return self.__indexed


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
        # Entity can update resource metadata
        CAN_UPDATE = 'CAN_UPDATE'

    def __init__(self):
        self.__entity = None
        self.__authorized = False

    @property
    def entity(self) -> Optional[Pairwise]:
        return self.__entity

    @property
    def authorized(self) -> bool:
        return self.__authorized

    async def authorize(self, entity: Pairwise) -> bool:
        """Authorize participant

        In DESCENDANTS may invoke adv. proof verify procedures...

        :param entity: Service Client
        :return: success
        """
        self.__entity = entity
        self.__authorized = True
        return self.__authorized

    def has_permissions(self) -> Set[PermissionLevel]:
        """
        :return: list of DataVault permissions for client
        """
        return {
            self.PermissionLevel.CAN_READ,
            self.PermissionLevel.CAN_WRITE,
            self.PermissionLevel.CAN_CREATE,
            self.PermissionLevel.CAN_UPDATE
        }

    @property
    def can_read(self) -> bool:
        return self.PermissionLevel.CAN_READ in self.has_permissions()

    @property
    def can_write(self) -> bool:
        return self.PermissionLevel.CAN_WRITE in self.has_permissions()

    @property
    def can_create(self) -> bool:
        return self.PermissionLevel.CAN_CREATE in self.has_permissions()

    @property
    def can_update(self) -> bool:
        return self.PermissionLevel.CAN_UPDATE in self.has_permissions()

    def validate(
            self, can_read: bool = False, can_write: bool = False,
            can_create: bool = False, can_update: bool = False, expected: Set[PermissionLevel] = None
    ):
        expected = list(expected) if expected else []
        permissions = self.has_permissions()
        if can_read:
            expected.append(ConfidentialStorageAuthProvider.PermissionLevel.CAN_READ)
        if can_write:
            expected.append(ConfidentialStorageAuthProvider.PermissionLevel.CAN_WRITE)
        if can_create:
            expected.append(ConfidentialStorageAuthProvider.PermissionLevel.CAN_CREATE)
        if can_update:
            expected.append(ConfidentialStorageAuthProvider.PermissionLevel.CAN_UPDATE)
        if not set(expected).issubset(permissions):
            expected_str = ','.join([p.value for p in expected])
            raise ConfidentialStoragePermissionDenied(f'Expected permissions: [{expected_str}]')


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
        type: str = 'X25519KeyAgreementKey2019'

        @property
        def is_filled(self) -> bool:
            if self.id or self.type:
                return True
            else:
                return False
    id: str
    # The entity or cryptographic key that is in control of the data vault.
    # The value is required and MUST be a URI. Example: "did:example:123456789"
    controller: str
    # A unique counter for the data vault in order to ensure that clients are
    # properly synchronized to the data vault. Example: 0
    sequence: int = 0
    # The root entities or cryptographic key(s) that are authorized to invoke an authorization capability
    # to modify the data vault's configuration or read or write to it.
    # The value is optional, but if present, MUST be a URI or an array of URIs.
    # When this value is not present, the value of controller property is used for the same purpose.
    invoker: Optional[Union[str, List[str]]] = None
    # The root entities or cryptographic key(s) that are authorized to delegate authorization capabilities
    # to modify the data vault's configuration or read or write to it.
    # The value is optional, but if present, MUST be a URI or an array of URIs.
    # When this value is not present, the value of controller property is used for the same purpose.
    delegator: Optional[Union[str, List[str]]] = None
    # Used to express an application-specific reference identifier.
    # The value is optional and, if present, MUST be a string.
    reference_id: Optional[str] = None
    # keyAgreementKey
    key_agreement: Optional[KeyAgreement] = None
    # HMAC
    hmac: Optional[HMAC] = None

    def as_json(self) -> dict:
        js = {
            'id': self.id,
            'sequence': self.sequence,
            'controller': self.controller,
        }
        if self.invoker:
            js['invoker'] = self.invoker
        if self.delegator:
            js['delegator'] = self.delegator
        if self.reference_id:
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
        self.id = js.get('id', None)
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
        hmac_type = hmac.get('type', None)
        if hmac_id or hmac_type:
            self.hmac = HMAC(
                hmac_id, hmac_type
            )
        else:
            self.hmac = None
        # Copy others
        for fld, value in js.items():
            self.__setattr__(fld, value)

    @staticmethod
    def create_from_json(js: dict) -> 'VaultConfig':
        inst = VaultConfig(id='id', controller='')
        inst.from_json(js)
        return inst


class ConfidentialStorageRawByteStorage(ABC):
    """Layer A: raw bytes storage (Cloud, DB, File-system, Mobile, etc)

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    def __init__(self, encryption: BaseStreamEncryption = None):
        self.__encryption = encryption

    @property
    def encryption(self) -> Optional[BaseStreamEncryption]:
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

    @abstractmethod
    async def exists(self, uri: str) -> bool:
        raise NotImplementedError


class EncryptedDataVault:
    """Layer B: Encrypted Vault Storage

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    def __init__(self, auth: ConfidentialStorageAuthProvider = None, cfg: VaultConfig = None):
        if auth is not None and auth.authorized is False:
            raise ConfidentialStoragePermissionDenied(f'Not authorized access')
        self.__auth = auth
        self._cfg = cfg
        if cfg is None and auth is not None and auth.authorized:
            their_did = auth.entity.their.did
            my_did = auth.entity.me.did
            my_vk = auth.entity.me.verkey
            if ':' not in their_did:
                their_did = f'did:peer:{their_did}'
            if ':' not in my_did:
                my_did = f'did:peer:{my_did}'
            if ':' not in my_vk:
                my_vk = f'did:key:{my_vk}'
            cfg = VaultConfig(
                id=f'did:edvs:{auth.entity.their.did}',
                sequence=0,
                controller=my_did,
                delegator=[their_did],
                key_agreement=VaultConfig.KeyAgreement(
                    id=my_vk,
                    type='X25519KeyAgreementKey2019'
                ),
                reference_id='default'
            )
        self._cfg = cfg

    @property
    def auth(self) -> ConfidentialStorageAuthProvider:
        return self.__auth

    @property
    def cfg(self) -> VaultConfig:
        return self._cfg

    class Indexes:

        @abstractmethod
        async def filter(self, **attributes) -> List[StructuredDocument]:
            raise NotImplementedError

    @abstractmethod
    async def open(self):
        raise NotImplementedError

    @abstractmethod
    async def close(self):
        raise NotImplementedError

    @abstractmethod
    async def indexes(self) -> Indexes:
        raise NotImplementedError

    @abstractmethod
    async def create_stream(self, uri: str, meta: Union[dict, StreamMeta] = None, chunk_size: int = None, **attributes) -> StructuredDocument:
        raise NotImplementedError

    @abstractmethod
    async def create_document(self, uri: str, meta: Union[dict, DocumentMeta] = None, **attributes) -> StructuredDocument:
        raise NotImplementedError

    @abstractmethod
    async def remove(self, uri: str):
        raise NotImplementedError

    @abstractmethod
    async def update(self, uri: str, meta: Union[dict, DocumentMeta, StreamMeta] = None, **attributes):
        raise NotImplementedError

    @abstractmethod
    async def load(self, uri: str) -> StructuredDocument:
        raise NotImplementedError

    @abstractmethod
    async def save_document(self, uri: str, doc: EncryptedDocument):
        raise NotImplementedError

    @abstractmethod
    async def readable(self, uri: str) -> AbstractReadOnlyStream:
        raise NotImplementedError

    @abstractmethod
    async def writable(self, uri: str) -> AbstractWriteOnlyStream:
        raise NotImplementedError
