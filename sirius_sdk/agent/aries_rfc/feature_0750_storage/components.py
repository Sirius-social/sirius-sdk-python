import io
from abc import ABC, abstractmethod
from typing import List, Optional
from contextlib import asynccontextmanager

from sirius_sdk.encryption import bytes_to_b58


class Encryption:

    def __init__(self, recipient_keys: List[str]):
        self.__recipient_keys = recipient_keys

    @property
    def recipient_keys(self) -> List[str]:
        return self.__recipient_keys


class EncReadOnlyStream(ABC):

    def __init__(self, urn: str, enc: Optional[Encryption] = None):
        self.__urn = urn
        self.__enc = enc
        self.__pos = 0

    @property
    def urn(self) -> str:
        return self.__urn

    @property
    def enc(self) -> Optional[Encryption]:
        return self.__enc

    @abstractmethod
    async def open(self):
        pass

    @abstractmethod
    async def close(self):
        pass

    @abstractmethod
    async def read(self, size: int = -1) -> bytes:
        pass

    @abstractmethod
    async def seek(self, pos: int) -> int:
        pass

    @abstractmethod
    async def eof(self) -> bool:
        pass

    async def read_chunked(self, chunk_size: int):
        pos = 0
        await self.seek(0)
        while not await self.eof():
            raw = await self.read(chunk_size)
            yield raw
            pos += chunk_size
            await self.seek(pos)


class EncWriteOnlyStream(ABC):

    def __init__(self, urn: str, enc: Optional[Encryption] = None):
        self.__urn = urn
        self.__enc = enc

    @property
    def urn(self) -> str:
        return self.__urn

    @property
    def enc(self) -> Optional[Encryption]:
        return self.__enc

    @abstractmethod
    async def write(self, data: bytes):
        pass

    @abstractmethod
    async def write_chunked(self, data: io.BytesIO, chunk_size: int):
        pass


class RawByteStorage:
    """Layer A: raw bytes storage (Cloud, DB, File-system, Mobile, etc)

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    pass


class EncryptedDataVault:
    """Layer B: Encrypted Vault Storage

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    class VaultConfig:
        pass

    class EncryptedDocument:
        pass

    class Indexes:
        pass


class Authorization:
    """Layer C: Authorization (policy enforcement point)

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """
    pass
