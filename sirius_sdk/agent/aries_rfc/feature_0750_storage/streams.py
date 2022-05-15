import io
from abc import ABC, abstractmethod
from typing import List, Optional

import aiofiles


class StreamEncryption:

    def __init__(self, recipient_keys: List[str]):
        """"Encryption settings for Streams

        :param recipient_keys: list of public keys of recipients, owner may control list of
            participants who have access to stream semantic
        """
        self.__recipient_keys = recipient_keys

    @property
    def recipient_keys(self) -> List[str]:
        return self.__recipient_keys


class AbstractStream(ABC):

    def __init__(self, path: str, chunk_size: int, enc: Optional[StreamEncryption] = None):
        """Interface for Low-level layers of Vault Storage

        :param path: path to resource
        :param chunk_size: size (in bytes) of chunks that stream was splitted to
          Chunks allow:
            - partially upload/download big data files/streams (control progress)
            - encrypt/decrypt big data partially
            - adv. services like upload/download with pause/resume (for cloud providers for example)
        :param enc: (optional) encoding config
        """
        self.__path = path
        self.__enc = enc
        self._position = 0
        self.__chunk_size = chunk_size

    @property
    def path(self) -> str:
        return self.__path

    @property
    def enc(self) -> Optional[StreamEncryption]:
        return self.__enc

    @property
    def position(self) -> int:
        return self._position

    @property
    def chunk_size(self) -> int:
        return self.__chunk_size

    @abstractmethod
    async def open(self):
        raise NotImplemented

    @abstractmethod
    async def close(self):
        raise NotImplemented

    @abstractmethod
    async def seek(self, pos: int) -> int:
        raise NotImplemented


class AbstractReadOnlyStream(AbstractStream):
    """Stream abstraction for reading operations:
      - cloud storage
      - file-system
      - external storages
      - etc
    """

    @abstractmethod
    async def read_chunk(self) -> bytes:
        raise NotImplemented

    @abstractmethod
    async def eof(self) -> bool:
        raise NotImplemented

    async def read(self) -> bytes:
        raw = b''
        async for chunk in self.read_chunked():
            raw += chunk
        return raw

    async def read_chunked(self):
        await self.seek(0)
        while not await self.eof():
            raw = await self.read_chunk()
            yield raw


class AbstractWriteOnlyStream(AbstractStream):
    """Stream abstraction for reading operations:
      -----------------------------------------------------------------------
      !!! Warning !!! Supposed chunk-write call has ATOMIC nature and persistent:
        expected Write stream should operate in non-buffering mode OR/AND flush every chunk.
      -----------------------------------------------------------------------

      - cloud storage
      - file-system
      - external storages
      - etc
    """

    @abstractmethod
    async def write_chunk(self, chunk: bytes):
        raise NotImplemented

    async def write(self, data: bytes):
        stream = io.BytesIO(data)
        stream.seek(0)
        while True:
            try:
                chunk = stream.read(self.chunk_size)
                if len(chunk) > 0:
                    await self.write_chunk(chunk)
                else:
                    return
            except EOFError:
                return

    async def copy(self, src: AbstractReadOnlyStream):
        accum = b''
        async for chunk in src.read_chunked():
            accum += chunk
            while len(accum) >= self.chunk_size:
                await self.write_chunk(accum[:self.chunk_size])
                accum = accum[self.chunk_size:]
            if await src.eof():
                await self.write_chunk(accum)
                return


class FileSystemReadOnlyStream(AbstractReadOnlyStream):

    def __init__(self, path: str, chunk_size: int, enc: Optional[StreamEncryption] = None):
        super().__init__(path, chunk_size, enc)
        self.__fd = None
        self.__size = 0

    async def open(self):
        self.__fd = await aiofiles.open(self.path, 'rb')
        self.__size = await self.__fd.seek(0, io.SEEK_END)
        await self.__fd.seek(0, io.SEEK_SET)

    async def close(self):
        if self.__fd:
            await self.__fd.close()
            self.__size = 0
            self.__fd = None

    async def seek(self, pos: int) -> int:
        if self.__fd:
            self._position = await self.__fd.seek(pos, io.SEEK_SET)
            return self._position
        else:
            raise RuntimeError('FileStream is not Opened')

    async def read_chunk(self) -> bytes:
        if self.__fd:
            raw = await self.__fd.read(self.chunk_size)
            self._position += len(raw)
            return raw
        else:
            raise RuntimeError('FileStream is not Opened')

    async def eof(self) -> bool:
        if self._position < self.__size:
            return False
        else:
            return True


class FileSystemWriteOnlyStream(AbstractWriteOnlyStream):

    def __init__(self, path: str, chunk_size: int, enc: Optional[StreamEncryption] = None):
        super().__init__(path, chunk_size, enc)
        self.__fd = None

    async def create(self, truncate: bool = False):
        async with aiofiles.open(self.path, 'w+b') as fd:
            if truncate:
                await fd.truncate(0)

    async def open(self):
        self.__fd = await aiofiles.open(self.path, 'wb', buffering=0)
        await self.__fd.seek(0, io.SEEK_SET)

    async def close(self):
        if self.__fd:
            await self.__fd.flush()
            await self.__fd.close()
            self.__fd = None

    async def seek(self, pos: int) -> int:
        if self.__fd:
            self._position = await self.__fd.seek(pos, io.SEEK_SET)
            return self._position
        else:
            raise RuntimeError('FileStream is not Opened')

    async def write_chunk(self, chunk: bytes):
        offset = await self.__fd.write(chunk)
        self._position += offset
