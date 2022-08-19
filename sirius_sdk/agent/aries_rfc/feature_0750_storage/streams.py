import io
import json
import struct
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import List, Optional, Dict

import nacl.utils
import nacl.bindings

import sirius_sdk
from sirius_sdk.encryption import b58_to_bytes, bytes_to_b58, bytes_to_b64
from sirius_sdk.encryption.ed25519 import prepare_pack_recipient_keys, locate_pack_recipient_key

from .encoding import ConfidentialStorageEncType
from .errors import StreamEncryptionError, StreamInitializationError


class BaseStreamEncryption:

    def __init__(self, nonce: str = None, type_: ConfidentialStorageEncType = ConfidentialStorageEncType.X25519KeyAgreementKey2019):
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
    def type(self) -> ConfidentialStorageEncType:
        return self.__type

    @property
    def cek(self) -> Optional[bytes]:
        return self._cek


class StreamEncryption(BaseStreamEncryption):

    def setup(self, target_verkeys: List[str]) -> "StreamEncryption":
        """Prepare for Encryption

        :param target_verkeys: list of base58 encoded target verkeys
        """
        if self.type != ConfidentialStorageEncType.X25519KeyAgreementKey2019:
            raise StreamEncryptionError(f'Unsupported key agreement "{self.type}"')
        recip_json, cek = prepare_pack_recipient_keys(
            to_verkeys=[b58_to_bytes(key) for key in target_verkeys]
        )
        recip = json.loads(recip_json)
        self._recipients = recip['recipients']
        self._cek = cek
        return self


class StreamDecryption(BaseStreamEncryption):

    def __init__(
            self, recipients: Dict = None, nonce: str = None,
            type_: ConfidentialStorageEncType = ConfidentialStorageEncType.X25519KeyAgreementKey2019
    ):
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

    def __init__(self, path: str, enc: Optional[BaseStreamEncryption] = None):
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
    def enc(self) -> Optional[BaseStreamEncryption]:
        return self.__enc

    @enc.setter
    def enc(self, value: BaseStreamEncryption):
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
            if self.enc.type == ConfidentialStorageEncType.UNKNOWN:
                return chunk
            elif self.enc.type == ConfidentialStorageEncType.X25519KeyAgreementKey2019:
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
                raise StreamEncryptionError('Unknown Encryption Type')
        else:
            return chunk

    async def decrypt(self, chunk: bytes) -> bytes:
        if self.enc:
            if self.enc.type == ConfidentialStorageEncType.UNKNOWN:
                return chunk
            elif self.enc.type == ConfidentialStorageEncType.X25519KeyAgreementKey2019:
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
                raise StreamEncryptionError('Unknown Encryption Type')
        else:
            return chunk

    def _build_recips(self, recipients: dict) -> dict:
        if self.enc.type == ConfidentialStorageEncType.X25519KeyAgreementKey2019:
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

    def __init__(self, path: str, chunks_num: int, enc: Optional[BaseStreamEncryption] = None):
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

    def __init__(self, path: str, chunk_size: int = 1024, enc: Optional[BaseStreamEncryption] = None):
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

    @abstractmethod
    async def truncate(self, no: int = 0):
        """Truncate stream content

        :param no: new stream size will bi limited chunk_no
        """
        raise NotImplemented

    async def copy(self, src: AbstractReadOnlyStream):
        if not src.is_open:
            raise StreamInitializationError('Source stream is closed!')
        async for chunk in src.read_chunked():
            await self.write_chunk(chunk)
            if await src.eof():
                return


