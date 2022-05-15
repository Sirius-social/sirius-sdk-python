import io
import json
import struct
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Union

import aiofiles
import nacl.utils
import nacl.bindings

from sirius_sdk.encryption import b58_to_bytes, bytes_to_b58
from sirius_sdk.encryption.ed25519 import prepare_pack_recipient_keys, locate_pack_recipient_key


class AbstractStreamEncryption(ABC):

    def __init__(self, recipients: Dict = None, nonce: str = None, type_: str = 'X25519KeyAgreementKey2019'):
        """"Encryption settings for Streams
        :param nonce: (base58 string) nonce bytes
        :param recipients: JWE.recipients document (example: https://identity.foundation/confidential-storage/#example-4-example-encrypted-document)
            participants who have access to stream semantic
        """
        if nonce is None:
            nonce = bytes_to_b58(nacl.utils.random(nacl.bindings.crypto_aead_chacha20poly1305_ietf_NPUBBYTES))
        self.__nonce = nonce
        self._recipients = recipients
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
        return self._recipients

    @recipients.setter
    def recipients(self, value: Dict = None):
        self._recipients = value

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
            raise RuntimeError(f'Unsupported key agreement "{self.type}"')
        recip_json, cek = prepare_pack_recipient_keys(
            to_verkeys=[b58_to_bytes(key) for key in target_verkeys]
        )
        recip = json.loads(recip_json)
        self._recipients = recip['recipients']
        self._cek = cek


class StreamDecryption(AbstractStreamEncryption):

    def setup(self, vk: str, sk: str):
        """Prepare for Decryption

        :param vk: (base58 string) decryption verkey
        :param sk: (base58 string) decryption sigkey
        """
        if self.recipients is None:
            raise RuntimeError('Recipients metadata in JWE format expected')
        cek, sender_vk, recip_vk_b58 = locate_pack_recipient_key(
            recipients=self.recipients, my_verkey=b58_to_bytes(vk), my_sigkey=b58_to_bytes(sk)
        )
        self._cek = cek


class AbstractStream(ABC):

    def __init__(self, path: str, chunk_size: int, enc: Optional[AbstractStreamEncryption] = None):
        """Interface for Low-level layers of Vault Storage

        :param path: path to resource
        :param chunk_size: size (in bytes) of chunks that stream was splitted to
          !!! stream may ignore chunk_size (when stream is encoded for example) !!!
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

    def __init__(self, path: str, chunk_size: int, enc: Optional[StreamDecryption] = None):
        super().__init__(path, chunk_size, enc)

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

    def __init__(self, path: str, chunk_size: int, enc: Optional[StreamEncryption] = None):
        super().__init__(path, chunk_size, enc)

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

    def __init__(self, path: str, chunk_size: int, enc: Optional[StreamDecryption] = None):
        super().__init__(path, chunk_size, enc)
        self.__fd = None
        self.__size = 0
        self.__nonce_b = None
        if enc:
            if enc.cek is None:
                raise RuntimeError('You passed "enc" param but not initialized it. Call setup() at first!')
            self.__nonce_b = b58_to_bytes(enc.nonce)

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
            if self.enc:
                # For encoded streams passed chunk_size will be ignored
                # Read header with encoded bytes size
                b = await self.__fd.read(4)
                self._position += len(b)
                if len(b) != 4:
                    raise RuntimeError('Unexpected encoded file structure')
                sz = struct.unpack("i", b)[0]
                # Read chunk
                encrypted = await self.__fd.read(sz)
                if len(encrypted) != sz:
                    raise RuntimeError('Unexpected encoded file structure')
                # Decode bytes stream
                decrypted = nacl.bindings.crypto_aead_chacha20poly1305_ietf_decrypt(
                    ciphertext=encrypted, aad=b'', nonce=self.__nonce_b, key=self.enc.cek
                )
                self._position += len(encrypted)
                return decrypted
            else:
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
        self.__cek = None
        self.__nonce_b = None
        if enc:
            if enc.type != 'X25519KeyAgreementKey2019':
                raise RuntimeError(f'Unsupported key agreement "{enc.type}"')
            if not enc.recipients:
                raise RuntimeError(f'Recipients data missed, call Setup first!')
            self.__nonce_b = b58_to_bytes(enc.nonce)
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
        self._position += offset
