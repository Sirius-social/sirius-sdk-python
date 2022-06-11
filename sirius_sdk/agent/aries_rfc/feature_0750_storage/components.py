from enum import Enum
from abc import ABC, abstractmethod
from typing import List, Union, Optional

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

    def __init__(self, entity: sirius_sdk.Pairwise):
        """
        :param entity: Service Client
        """
        self.__entity = entity

    @property
    def entity(self) -> sirius_sdk.Pairwise:
        return self.__entity

    async def has_permissions(self) -> List[PermissionLevel]:
        """
        :return: list of DataVault permissions for client
        """
        return [
            self.PermissionLevel.CAN_READ,
            self.PermissionLevel.CAN_WRITE,
            self.PermissionLevel.CAN_CREATE
        ]

    async def can_read(self) -> bool:
        return self.PermissionLevel.CAN_READ in await self.has_permissions()

    async def can_write(self) -> bool:
        return self.PermissionLevel.CAN_WRITE in await self.has_permissions()

    async def can_create(self) -> bool:
        return self.PermissionLevel.CAN_CREATE in await self.has_permissions()


class EncryptedDataVault:
    """Layer B: Encrypted Vault Storage

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    class VaultConfig:
        pass

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
