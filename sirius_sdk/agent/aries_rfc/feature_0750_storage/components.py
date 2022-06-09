import os
from abc import ABC, abstractmethod
from typing import List, Optional, Union
from urllib.parse import urlparse
from contextlib import asynccontextmanager

import aiofiles

from sirius_sdk.encryption import bytes_to_b58
from .streams import AbstractReadOnlyStream, AbstractWriteOnlyStream, FileSystemReadOnlyStream, FileSystemWriteOnlyStream
from .documents import EncryptedDocument, Document


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


class RawByteStorage(ABC):
    """Layer A: raw bytes storage (Cloud, DB, File-system, Mobile, etc)

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    @abstractmethod
    async def make_document(self, id_: str) -> Document:
        raise NotImplementedError

    @abstractmethod
    async def make_readable_stream(self, uri: str, chunks_num: int) -> AbstractReadOnlyStream:
        raise NotImplementedError

    @abstractmethod
    async def make_writable_stream(self, uri: str) -> AbstractReadOnlyStream:
        raise NotImplementedError


class FileSystemByteStorage(RawByteStorage):

    async def make_document(self, id_: str) -> Document:
        path = self.__uri_to_path(id_)
        if os.path.isfile(path):
            doc = Document()
            async with aiofiles.open(path, 'rb') as f:
                doc.content = await f.read()
            return doc
        else:
            raise RuntimeError

    async def make_readable_stream(self, uri: str, chunks_num: int) -> AbstractReadOnlyStream:
        path = self.__uri_to_path(uri)
        if os.path.isfile(path):
            stream = FileSystemReadOnlyStream(path, chunks_num=chunks_num)
            return stream

    async def make_writable_stream(self, uri: str) -> AbstractReadOnlyStream:
        pass

    @staticmethod
    def __uri_to_path(uri: str) -> str:
        p = urlparse(uri)
        path = os.path.abspath(os.path.join(p.netloc, p.path))
        return path


class EncryptedDataVault:
    """Layer B: Encrypted Vault Storage

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    class VaultConfig:
        pass

    class Indexes:
        async def apply(self, **filters) -> List[StructuredDocument]:
            pass


class AuthProvider:
    """Layer C: Authorization (policy enforcement point)

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """
    pass
