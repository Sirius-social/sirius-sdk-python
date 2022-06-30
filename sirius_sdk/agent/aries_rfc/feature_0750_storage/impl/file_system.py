import io
import math
import os
import struct
from typing import Optional
from urllib.parse import urlparse

import aiofiles

from sirius_sdk.agent.aries_rfc.feature_0750_storage import AbstractReadOnlyStream, StreamDecryption, \
    StreamInitializationError, ConfidentialStorageEncType, StreamEncryptionError, StreamSeekableError, StreamEOF, \
    StreamFormatError, AbstractWriteOnlyStream, StreamEncryption
from sirius_sdk.agent.aries_rfc.feature_0750_storage.components import ConfidentialStorageRawByteStorage, ConfidentialStorageAuthProvider
from sirius_sdk.errors.exceptions import SiriusInitializationError
from sirius_sdk.hub import _current_hub


class FileSystemReadOnlyStream(AbstractReadOnlyStream):

    def __init__(self, path: str, chunks_num: int, enc: Optional[StreamDecryption] = None):
        if chunks_num <= 0:
            raise StreamInitializationError('Chunks Num must be greater than 0')
        super().__init__(path, chunks_num, enc)
        self.__fd = None
        self.__size = 0
        self.__chunk_size = 0
        self.__chunk_offsets = []
        if enc:
            if enc.type != ConfidentialStorageEncType.UNKNOWN:
                if enc.cek is None:
                    try:
                        hub = _current_hub()
                        crypto_manager_exists = hub.get_crypto() is not None
                        if crypto_manager_exists is False:
                            raise StreamEncryptionError(
                                'Crypto manager is not configured'
                            )
                    except SiriusInitializationError:
                        raise StreamEncryptionError(
                            'You should initialize SDK or Call setup() to manually pass keys for decoder'
                        )

    async def open(self):
        if self.__fd:
            return
        self.__fd = await aiofiles.open(self.path, 'rb')
        self.__size = await self.__fd.seek(0, io.SEEK_END)
        await self.__fd.seek(0, io.SEEK_SET)
        if self.enc:
            await self.__load_enc_chunks()
            self.__chunk_size = self.__chunk_offsets[0][0]
        else:
            self.__chunk_size = math.ceil(self.__size / self.chunks_num)
        self._seekable = True
        self._is_open = True

    async def close(self):
        if self.__fd:
            await self.__fd.close()
            self.__size = 0
            self.__fd = None
            self._seekable = None
            self._is_open = False
            self.__chunk_offsets.clear()

    async def seek_to_chunk(self, no: int) -> int:
        self.__assert_is_open()
        if not self._seekable:
            raise StreamSeekableError('Stream is not seekable')
        pos = no * self.__chunk_size
        if pos > self.__size:
            raise StreamEOF('EOF')
        else:
            new_pos = await self.__fd.seek(pos, io.SEEK_SET)
            self._current_chunk = math.trunc(new_pos / self.__chunk_size)
            return self._current_chunk

    async def read_chunk(self, no: int = None) -> (int, bytes):
        """Read next chunk

        :param no: int (optional) chunk offset, None if reading from current offset
        :raises StreamEOF if end of stream

        :return (new-chunk-offset, data)
        """
        self.__assert_is_open()
        if no is not None:
            await self.seek_to_chunk(no)
        if self._current_chunk >= self.chunks_num:
            raise StreamEOF('EOF')
        file_pos = self._current_chunk * self.__chunk_size
        if self.enc:
            if self._current_chunk >= self.chunks_num:
                raise StreamEOF('EOF')
            info = self.__chunk_offsets[self._current_chunk]
            sz_to_read = info[0]
            seek_to = info[1]
            await self.__fd.seek(seek_to)
            encrypted = await self.__fd.read(sz_to_read)
            if len(encrypted) != sz_to_read:
                raise StreamFormatError('Unexpected encoded file structure')
            # Decode bytes stream
            decrypted = await self.decrypt(encrypted)
            file_pos += len(encrypted)
            self._current_chunk += 1
            return self._current_chunk, decrypted
        else:
            raw = await self.__fd.read(self.__chunk_size)
            self._current_chunk += 1
            return self._current_chunk, raw

    async def eof(self) -> bool:
        self.__assert_is_open()
        if self._current_chunk < self.chunks_num:
            return False
        else:
            return True

    async def __load_enc_chunks(self):
        file_pos = 0
        self.__chunk_offsets.clear()
        while file_pos < self.__size:
            b = await self.__fd.read(4)
            file_pos += len(b)
            if len(b) != 4:
                raise StreamFormatError('Unexpected encoded file structure')
            sz = struct.unpack("i", b)[0]
            self.__chunk_offsets.append([sz, file_pos])
            file_pos = await self.__fd.seek(sz, io.SEEK_CUR)

    def __assert_is_open(self):
        if not self.__fd:
            raise StreamInitializationError('FileStream is not Opened!')


class FileSystemWriteOnlyStream(AbstractWriteOnlyStream):

    DEF_CHUNK_SIZE = 1024  # 1KB

    def __init__(self, path: str, chunk_size: int = DEF_CHUNK_SIZE, enc: Optional[StreamEncryption] = None):
        super().__init__(path, chunk_size, enc)
        self.__cek = None
        self.__file_size = 0
        self.__file_pos = 0
        self.__chunk_offsets = []
        if enc:
            if enc.type != ConfidentialStorageEncType.UNKNOWN:
                if enc.type != ConfidentialStorageEncType.X25519KeyAgreementKey2019:
                    raise StreamEncryptionError(f'Unsupported key agreement "{enc.type}"')
                if not enc.recipients:
                    raise StreamEncryptionError(f'Recipients data missed, call Setup first!')
        self.__fd = None

    async def create(self, truncate: bool = False):
        async with aiofiles.open(self.path, 'w+b') as fd:
            if truncate:
                await fd.truncate(0)

    async def open(self):
        self.__fd = await aiofiles.open(self.path, 'a+b', buffering=0)
        file_is_seekable = await self.__fd.seekable()
        self._seekable = file_is_seekable
        self.__file_pos = await self.__fd.seek(0, io.SEEK_END)
        self.__file_size = self.__file_pos
        if self.enc:
            await self.__fd.seek(0, io.SEEK_SET)
            await self.__load_enc_chunks()
            await self.__fd.seek(0, io.SEEK_END)
            self._chunks_num = len(self.__chunk_offsets)
            self._current_chunk = self._chunks_num
        else:
            self._current_chunk = math.trunc(self.__file_pos / self._chunk_size)
            self._chunks_num = self._current_chunk
        self._is_open = True

    async def close(self):
        if self.__fd:
            await self.__fd.flush()
            await self.__fd.close()
            self.__fd = None
            self._seekable = None
            self.__file_size = 0
            self.__file_pos = 0
            self._is_open = False
            self.__chunk_offsets.clear()

    async def seek_to_chunk(self, no: int) -> int:
        self.__assert_is_open()
        if no == self._current_chunk:
            return no
        elif no == self._chunks_num:
            self._current_chunk = self._chunks_num
            return self._current_chunk
        elif no > self._chunks_num:
            raise StreamEOF('EOF')
        if self.__chunk_offsets:
            try:
                sz, file_pos = self.__chunk_offsets[no]
            except IndexError:
                raise StreamEOF('Chunk No out of range')
        else:
            file_pos = no * self._chunk_size
        if file_pos > self.__file_size:
            raise StreamEOF('EOF')
        else:
            file_pos = await self.__fd.seek(file_pos, io.SEEK_SET)
            self._current_chunk = math.trunc(file_pos / self._chunk_size)
            self.__file_pos = file_pos
            return self._current_chunk

    async def write_chunk(self, chunk: bytes, no: int = None) -> (int, int):
        self.__assert_is_open()
        if no is not None:
            await self.seek_to_chunk(no)
        if self.enc:
            # encode
            encoded = await self.encrypt(chunk)
            # Write Chunk Header with actual encoded bytes size
            sz = len(encoded)
            offset1 = await self.__fd.write(struct.pack("i", sz))
            offset2 = await self.__fd.write(encoded)
            offset = offset1 + offset2
            if no is not None and no < len(self.__chunk_offsets):
                self.__chunk_offsets[no] = (sz, self.__file_pos)
            else:
                self.__chunk_offsets.append((sz, self.__file_pos))
        else:
            offset = await self.__fd.write(chunk)
        self.__file_pos += offset
        if self.__file_pos >= self.__file_size:
            self.__file_size += self.__file_pos - self.__file_size
            self._chunks_num += 1
        self._current_chunk += 1
        return self._current_chunk, len(chunk)

    async def truncate(self, no: int = 0):
        self.__assert_is_open()
        if no == 0:
            await self.__fd.truncate(0)
            await self.__fd.flush()
            self._current_chunk = 0
            self._chunks_num = 0
        else:
            if self.__chunk_offsets:
                max_chunk_offset = len(self.__chunk_offsets)
                if no >= max_chunk_offset:
                    return
                else:
                    sz, file_pos = self.__chunk_offsets[no]
                    await self.__fd.truncate(file_pos)
                    await self.__fd.flush()
                    self.__chunk_offsets = self.__chunk_offsets[:no]
                    self._chunks_num = len(self.__chunk_offsets)
                    if self._current_chunk > no:
                        await self.seek_to_chunk(no)
            else:
                file_pos = no * self._chunk_size
                if file_pos >= self.__file_size:
                    return self._chunks_num
                else:
                    await self.__fd.truncate(file_pos)
                    await self.__fd.flush()
                    self._chunks_num = no
                    if self._current_chunk > no:
                        await self.seek_to_chunk(no)

    async def __load_enc_chunks(self):
        file_pos = 0
        self.__chunk_offsets.clear()
        while file_pos < self.__file_size:
            b = await self.__fd.read(4)
            file_pos += len(b)
            if len(b) != 4:
                raise StreamFormatError('Unexpected encoded file structure')
            sz = struct.unpack("i", b)[0]
            self.__chunk_offsets.append([sz, file_pos])
            file_pos = await self.__fd.seek(sz, io.SEEK_CUR)

    def __assert_is_open(self):
        if not self.__fd:
            raise StreamInitializationError('FileStream is not Opened')


class FileSystemRawByteStorage(ConfidentialStorageRawByteStorage):

    async def create(self, uri: str):
        path = self.__uri_to_path(uri)
        if os.path.isfile(path):
            raise StreamInitializationError(f'Stream with URI: {uri} already exists!')
        else:
            stream = FileSystemWriteOnlyStream(path)
            await stream.create()

    async def remove(self, uri: str):
        path = self.__uri_to_path(uri)
        if os.path.isfile(path):
            os.remove(path)

    async def readable(self, uri: str, chunks_num: int) -> AbstractReadOnlyStream:
        path = self.__uri_to_path(uri)
        if not os.path.isfile(path):
            raise StreamInitializationError(f'Stream with URI: {uri} doe not exists!')
        return FileSystemReadOnlyStream(path=path, chunks_num=chunks_num)

    async def writeable(self, uri: str) -> AbstractWriteOnlyStream:
        path = self.__uri_to_path(uri)
        if not os.path.isfile(path):
            raise StreamInitializationError(f'Stream with URI: {uri} doe not exists!')
        return FileSystemWriteOnlyStream(path=path)

    @staticmethod
    def __uri_to_path(uri: str) -> str:
        p = urlparse(uri)
        path = os.path.abspath(os.path.join(p.netloc, p.path))
        return path