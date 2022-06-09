import io
import json
import math
import struct
from enum import Enum
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import List, Optional, Dict

import aiofiles
import nacl.utils
import nacl.bindings

import sirius_sdk
from sirius_sdk.errors.exceptions import SiriusInitializationError
from sirius_sdk.hub.core import _current_hub
from sirius_sdk.encryption import b58_to_bytes, bytes_to_b58, bytes_to_b64
from sirius_sdk.encryption.ed25519 import prepare_pack_recipient_keys, locate_pack_recipient_key

from .errors import StreamEOF, StreamEncryptionError, StreamInitializationError, \
    StreamSeekableError, StreamFormatError


class StreamEncType(Enum):
    # This enc-type typically used to save chunked structure of stream
    # that was encoded outside (on upper levels)
    UNKNOWN = 'UNKNOWN'
    # X25519
    X25519KeyAgreementKey2019 = 'X25519KeyAgreementKey2019'


class AbstractStreamEncryption(ABC):

    def __init__(self, nonce: str = None, type_: StreamEncType = StreamEncType.X25519KeyAgreementKey2019):
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
    def type(self) -> StreamEncType:
        return self.__type

    @property
    def cek(self) -> Optional[bytes]:
        return self._cek


class StreamEncryption(AbstractStreamEncryption):

    def setup(self, target_verkeys: List[str]) -> "StreamEncryption":
        """Prepare for Encryption

        :param target_verkeys: list of base58 encoded target verkeys
        """
        if self.type != StreamEncType.X25519KeyAgreementKey2019:
            raise StreamEncryptionError(f'Unsupported key agreement "{self.type}"')
        recip_json, cek = prepare_pack_recipient_keys(
            to_verkeys=[b58_to_bytes(key) for key in target_verkeys]
        )
        recip = json.loads(recip_json)
        self._recipients = recip['recipients']
        self._cek = cek
        return self


class StreamDecryption(AbstractStreamEncryption):

    def __init__(self, recipients: Dict = None, nonce: str = None, type_: StreamEncType = StreamEncType.X25519KeyAgreementKey2019):
        super().__init__(nonce, type_)
        self._recipients = recipients

    def setup(self, vk: str, sk: str) -> "StreamDecryption":
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
        return self


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
        self._is_open: bool = False

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def path(self) -> str:
        return self.__path

    @property
    def enc(self) -> Optional[StreamEncryption]:
        return self.__enc

    @enc.setter
    def enc(self, value: StreamEncryption):
        self.__enc = value

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

    async def encrypt(self, chunk: bytes) -> bytes:
        if self.enc:
            if self.enc.type == StreamEncType.UNKNOWN:
                return chunk
            else:
                mlen = len(chunk)
                prefix = struct.pack("i", mlen)
                nonce_bytes = b58_to_bytes(self.enc.nonce)
                aad = self._build_aad(self.enc.recipients)
                encoded = nacl.bindings.crypto_aead_chacha20poly1305_ietf_encrypt(
                    chunk, aad=aad, nonce=nonce_bytes, key=self.enc.cek
                )
                payload = prefix + encoded
                return payload
        else:
            return chunk

    async def decrypt(self, chunk: bytes) -> bytes:
        if self.enc:
            if self.enc.type == StreamEncType.UNKNOWN:
                return chunk
            else:
                nonce_bytes = b58_to_bytes(self.enc.nonce)
                prefix = chunk[:4]
                payload = chunk[4:]
                mlen = struct.unpack("i", prefix)[0]
                if self.enc.cek:
                    aad = self._build_aad(self.enc.recipients)
                    # Use manually configured encryption settings: [public-key, secret-key]
                    decrypted = nacl.bindings.crypto_aead_chacha20poly1305_ietf_decrypt(
                        ciphertext=payload, aad=aad, nonce=nonce_bytes, key=self.enc.cek
                    )
                else:
                    # Use Wallet to decrypt with previously configured SDK
                    recips = self._build_recips(self.enc.recipients)
                    recips_b64 = bytes_to_b64(json.dumps(recips).encode("ascii"), urlsafe=True)
                    ciphertext = payload[:mlen]
                    tag = payload[mlen:]
                    packed_message = OrderedDict(
                        [
                            ("protected", recips_b64),
                            ("iv", bytes_to_b64(nonce_bytes, urlsafe=True)),
                            ("ciphertext", bytes_to_b64(ciphertext, urlsafe=True)),
                            ("tag", bytes_to_b64(tag, urlsafe=True)),
                        ]
                    )
                    jwe = json.dumps(packed_message).encode()
                    unpacked = await sirius_sdk.Crypto.unpack_message(jwe)
                    decrypted = unpacked['message'].encode()
                return decrypted
        else:
            return chunk

    def _build_recips(self, recipients: dict) -> dict:
        if self.enc.type == StreamEncType.X25519KeyAgreementKey2019:
            recips = OrderedDict(
                [
                    ("enc", "xchacha20poly1305_ietf"),
                    ("typ", "JWM/1.0"),
                    ("alg", "Anoncrypt"),
                    ("recipients", recipients),
                ]
            )
            return recips
        else:
            raise StreamEncryptionError('Unknown encryption format')

    def _build_aad(self, recipients: dict) -> bytes:
        recips = self._build_recips(recipients)
        recips_json = json.dumps(recips)
        recips_b64 = bytes_to_b64(recips_json.encode("ascii"), urlsafe=True)
        aad = recips_b64.encode("ascii")
        return aad


class AbstractReadOnlyStream(AbstractStream):
    """Stream abstraction for reading operations:
      - cloud storage
      - file-system
      - external storages
      - etc
    """

    def __init__(self, path: str, chunks_num: int, enc: Optional[StreamDecryption] = None):
        """
        :param path: path to stream on local infrastructure (device, cloud provider ...)
        :param chunks_num: count of chunks that stream was splitted to
          !!! stream may ignore chunks_num (when stream is encoded for example) !!!
          Chunks allow:
            - partially upload/download big data files/streams (control progress)
            - encrypt/decrypt big data partially
            - adv. services like upload/download with pause/resume (for cloud providers for example)
        :param enc: allow decrypt stream chunks
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
                _, chunk = await src.read_chunk()
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

    def __init__(self, path: str, chunk_size: int = 1024, enc: Optional[StreamEncryption] = None):
        """
        :param chunk_size: size (in bytes) of chunks that stream was splitted to
          !!! actual chunks-sizes may be different (when stream is encoded for example) !!!
          Chunks allow:
            - partially upload/download big data files/streams (control progress)
            - encrypt/decrypt big data partially
            - adv. services like upload/download with pause/resume (for cloud providers for example)
        :param enc: allow encrypt stream chunks
        """
        super().__init__(path, enc)
        self.chunk_size = chunk_size

    @property
    def chunk_size(self) -> int:
        return self._chunk_size

    @chunk_size.setter
    def chunk_size(self, value: int):
        if value <= 0:
            raise StreamInitializationError('Chunk Size must to be > 0 !')
        self._chunk_size = value

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
                chunk = stream.read(self.chunk_size)
                if len(chunk) > 0:
                    await self.write_chunk(chunk)
                else:
                    return
            except EOFError:
                return

    async def copy(self, src: AbstractReadOnlyStream):
        if not src.is_open:
            raise StreamInitializationError('Source stream is closed!')
        async for chunk in src.read_chunked():
            await self.write_chunk(chunk)
            if await src.eof():
                return


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
            if enc.type != StreamEncType.UNKNOWN:
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
            if enc.type != StreamEncType.UNKNOWN:
                if enc.type != StreamEncType.X25519KeyAgreementKey2019:
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
        else:
            offset = await self.__fd.write(chunk)
        self.__file_pos += offset
        if self.__file_pos >= self.__file_size:
            self.__file_size += self.__file_pos - self.__file_size
            self._chunks_num += 1
        self._current_chunk += 1
        return self._current_chunk, len(chunk)

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
