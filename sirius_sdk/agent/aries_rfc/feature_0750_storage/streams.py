import io
import json
import math
import struct
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Union

import aiofiles
import nacl.utils
import nacl.bindings

from sirius_sdk.encryption import b58_to_bytes, bytes_to_b58
from sirius_sdk.encryption.ed25519 import prepare_pack_recipient_keys, locate_pack_recipient_key


class BaseStreamError(RuntimeError):

    def __init__(self, message):
        super().__init__(message)

    @property
    def message(self) -> str:
        return self.args[0] if self.args else ''


class StreamEOF(BaseStreamError):
    pass


class StreamEncryptionError(BaseStreamError):
    pass


class StreamInitializationError(BaseStreamError):
    pass


class StreamSeekableError(BaseStreamError):
    pass


class StreamFormatError(BaseStreamError):
    pass


class StreamTimeoutOccurred(BaseStreamError):
    pass


class AbstractStreamEncryption(ABC):

    def __init__(self, nonce: str = None, type_: str = 'X25519KeyAgreementKey2019'):
        """"Encryption settings for Streams
        :param nonce: (base58 string) nonce bytes
        """
        if nonce is None:
            nonce = bytes_to_b58(nacl.utils.random(nacl.bindings.crypto_aead_chacha20poly1305_ietf_NPUBBYTES))
        self.__nonce = nonce
        self._recipients = None
        self.__type = type_
        self._cek = None

    @property
    def nonce(self) -> str:
        return self.__nonce

    @nonce.setter
    def nonce(self, value: str):
        self.__nonce = value

    @property
    def recipients(self) -> Optional[Dict]:
        """JWE.recipients document (example: https://identity.foundation/confidential-storage/#example-4-example-encrypted-document)
        """
        return self._recipients

    @property
    def type(self) -> str:
        return self.__type

    @property
    def cek(self) -> Optional[bytes]:
        return self._cek


class StreamEncryption(AbstractStreamEncryption):

    def setup(self, target_verkeys: List[str]):
        """Prepare for Encryption

        :param target_verkeys: list of base58 encoded target verkeys
        """
        if self.type != 'X25519KeyAgreementKey2019':
            raise StreamEncryptionError(f'Unsupported key agreement "{self.type}"')
        recip_json, cek = prepare_pack_recipient_keys(
            to_verkeys=[b58_to_bytes(key) for key in target_verkeys]
        )
        recip = json.loads(recip_json)
        self._recipients = recip['recipients']
        self._cek = cek


class StreamDecryption(AbstractStreamEncryption):

    def __init__(self, recipients: Dict = None, nonce: str = None, type_: str = 'X25519KeyAgreementKey2019'):
        super().__init__(nonce, type_)
        self._recipients = recipients

    def setup(self, vk: str, sk: str):
        """Prepare for Decryption

        :param vk: (base58 string) decryption verkey
        :param sk: (base58 string) decryption sigkey
        """
        if self.recipients is None:
            raise StreamEncryptionError('Recipients metadata in JWE format expected')
        cek, sender_vk, recip_vk_b58 = locate_pack_recipient_key(
            recipients=self.recipients, my_verkey=b58_to_bytes(vk), my_sigkey=b58_to_bytes(sk)
        )
        self._cek = cek


class AbstractStream(ABC):

    def __init__(self, path: str, enc: Optional[AbstractStreamEncryption] = None):
        """Interface for Low-level layers of Vault Storage

        :param path: path to resource
        :param enc: (optional) encoding config
        """
        self.__path = path
        self.__enc = enc
        self._current_chunk = 0
        self._seekable = None
        self._chunks_num: int = 0

    @property
    def path(self) -> str:
        return self.__path

    @property
    def enc(self) -> Optional[StreamEncryption]:
        return self.__enc

    @property
    def seekable(self) -> Optional[bool]:
        return self._seekable

    @property
    def chunks_num(self) -> int:
        return self._chunks_num

    @property
    def current_chunk(self) -> int:
        """Stream offset"""
        return self._current_chunk

    @abstractmethod
    async def open(self):
        raise NotImplemented

    @abstractmethod
    async def close(self):
        raise NotImplemented

    @abstractmethod
    async def seek_to_chunk(self, no: int) -> int:
        raise NotImplemented


class AbstractReadOnlyStream(AbstractStream):
    """Stream abstraction for reading operations:
      - cloud storage
      - file-system
      - external storages
      - etc
    """

    def __init__(self, path: str, chunks_num: int, enc: Optional[StreamDecryption] = None):
        """
        :param chunks_num: count of chunks that stream was splitted to
          !!! stream may ignore chunks_num (when stream is encoded for example) !!!
          Chunks allow:
            - partially upload/download big data files/streams (control progress)
            - encrypt/decrypt big data partially
            - adv. services like upload/download with pause/resume (for cloud providers for example)
        """
        super().__init__(path, enc)
        self._chunks_num = chunks_num

    @abstractmethod
    async def read_chunk(self, no: int = None) -> (int, bytes):
        """Read next chunk

        :param no: int (optional) chunk offset, None if reading from current offset
        :raises StreamEOF if end of stream

        :return (new-chunk-offset, data)
        """
        raise NotImplemented

    async def decrypt(self, chunk: bytes) -> bytes:
        if self.enc:
            raise NotImplemented
        else:
            return chunk

    @abstractmethod
    async def eof(self) -> bool:
        raise NotImplemented

    async def read(self) -> bytes:
        raw = b''
        async for chunk in self.read_chunked():
            raw += chunk
        return raw

    async def read_chunked(self, src: "AbstractReadOnlyStream" = None):
        if src is None:
            await self.seek_to_chunk(0)
            while not await self.eof():
                _, raw = await self.read_chunk()
                yield raw
        else:
            await src.seek_to_chunk(0)
            while not await src.eof():
                _, chunk = await self.read_chunk()
                raw = await self.decrypt(chunk)
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

    def __init__(self, path: str, chunk_size: int, enc: Optional[StreamEncryption] = None):
        """
        :param chunk_size: size (in bytes) of chunks that stream was splitted to
          !!! actual chunks-sizes may be different (when stream is encoded for example) !!!
          Chunks allow:
            - partially upload/download big data files/streams (control progress)
            - encrypt/decrypt big data partially
            - adv. services like upload/download with pause/resume (for cloud providers for example)"""
        super().__init__(path, enc)
        self._chunk_size = chunk_size

    @abstractmethod
    async def write_chunk(self, chunk: bytes, no: int = None) -> (int, int):
        """Write new chunk to stream

        :param chunk: data bytes
        :param no: int (optional) chunk offset, None if writing to end of stream
        :return: (new-chunk-offset, writen data size)
        """
        raise NotImplemented

    async def write(self, data: bytes):
        stream = io.BytesIO(data)
        stream.seek(0)
        while True:
            try:
                chunk = stream.read(self._chunk_size)
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
            while len(accum) >= self._chunk_size:
                await self.write_chunk(accum[:self._chunk_size])
                accum = accum[self._chunk_size:]
            if await src.eof():
                await self.write_chunk(accum)
                return


class FileSystemReadOnlyStream(AbstractReadOnlyStream):

    def __init__(self, path: str, chunks_num: int, enc: Optional[StreamDecryption] = None):
        if chunks_num <= 0:
            raise StreamInitializationError('Chunks Num must be greater than 0')
        super().__init__(path, chunks_num, enc)
        self.__fd = None
        self.__size = 0
        self.__nonce_b = None
        self.__chunk_size = 0
        self.__chunk_offsets = []
        if enc:
            if enc.cek is None:
                raise StreamEncryptionError('You passed "enc" param but not initialized it. Call setup() at first!')
            self.__nonce_b = b58_to_bytes(enc.nonce)

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

    async def close(self):
        if self.__fd:
            await self.__fd.close()
            self.__size = 0
            self.__fd = None
            self._seekable = None
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

    async def decrypt(self, chunk: bytes) -> bytes:
        if self.enc:
            decrypted = nacl.bindings.crypto_aead_chacha20poly1305_ietf_decrypt(
                ciphertext=chunk, aad=b'', nonce=self.__nonce_b, key=self.enc.cek
            )
            return decrypted
        else:
            return chunk

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

    def __init__(self, path: str, chunk_size: int, enc: Optional[StreamEncryption] = None):
        super().__init__(path, chunk_size, enc)
        self.__cek = None
        self.__nonce_b = None
        self.__file_size = 0
        self.__file_pos = 0
        if enc:
            if enc.type != 'X25519KeyAgreementKey2019':
                raise StreamEncryptionError(f'Unsupported key agreement "{enc.type}"')
            if not enc.recipients:
                raise StreamEncryptionError(f'Recipients data missed, call Setup first!')
            self.__nonce_b = b58_to_bytes(enc.nonce)
        self.__fd = None

    async def create(self, truncate: bool = False):
        async with aiofiles.open(self.path, 'w+b') as fd:
            if truncate:
                await fd.truncate(0)

    async def open(self):
        self.__fd = await aiofiles.open(self.path, 'wb', buffering=0)
        await self.__fd.seek(0, io.SEEK_SET)
        self._seekable = self.enc is None
        self.__file_size = 0
        self.__file_pos = 0

    async def close(self):
        if self.__fd:
            await self.__fd.flush()
            await self.__fd.close()
            self.__fd = None
            self._seekable = None
            self.__file_size = 0
            self.__file_pos = 0

    async def seek_to_chunk(self, no: int) -> int:
        self.__assert_is_open()
        if not self._seekable:
            raise StreamSeekableError('Stream is not seekable')
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
            encoded = nacl.bindings.crypto_aead_chacha20poly1305_ietf_encrypt(
                chunk, aad=b'', nonce=self.__nonce_b, key=self.enc.cek
            )
            # Write Chunk Header with actual encoded bytes size
            sz = len(encoded)
            offset1 = await self.__fd.write(struct.pack("i", sz))
            offset2 = await self.__fd.write(encoded)
            offset = offset1 + offset2
        else:
            offset = await self.__fd.write(chunk)
        self.__file_pos += offset
        if self.__file_pos >= self.__file_size:
            self.__file_size += self.__file_pos - self.__file_size
            self._chunks_num += 1
        self._current_chunk += 1
        return self._current_chunk, len(chunk)

    def __assert_is_open(self):
        if not self.__fd:
            raise StreamInitializationError('FileStream is not Opened')
