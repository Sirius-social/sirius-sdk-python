import json
import base64
from typing import Any, Optional

from sirius_sdk.abstract.api import APICrypto
from sirius_sdk.abstract.storage import AbstractKeyValueStorage
from sirius_sdk.encryption import ed25519
from sirius_sdk.encryption import b58_to_bytes
from sirius_sdk.errors.exceptions import SiriusCryptoError
from sirius_sdk.hub.defaults.default_storage import InMemoryKeyValueStorage


class DefaultCryptoService(APICrypto):

    DB_KEYS = 'crypto_keys'
    DB_META = 'crypto_metadata'

    def __init__(self, storage: AbstractKeyValueStorage = None):
        self.storage = storage or InMemoryKeyValueStorage()

    async def create_key(self, seed: str = None, crypto_type: str = None) -> str:
        pk_bytes, sk_bytes = ed25519.create_keypair(seed.encode() if seed else None)
        pk_b58 = ed25519.bytes_to_b58(pk_bytes)
        await self.storage.select_db(self.DB_KEYS)
        await self.storage.set(pk_b58, sk_bytes)
        return pk_b58

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        await self.__check_verkey_exists(verkey)
        await self.storage.select_db(self.DB_META)
        await self.storage.set(verkey, metadata)

    async def get_key_metadata(self, verkey: str) -> Optional[dict]:
        await self.__check_verkey_exists(verkey)
        await self.storage.select_db(self.DB_META)
        meta = await self.storage.get(verkey)
        return meta

    async def crypto_sign(self, signer_vk: str, msg: bytes) -> bytes:
        await self.__check_verkey_exists(signer_vk)
        await self.storage.select_db(self.DB_KEYS)
        sk_bytes = await self.storage.get(signer_vk)
        signed = ed25519.sign_message(msg, sk_bytes)
        return signed

    async def crypto_verify(self, signer_vk: str, msg: bytes, signature: bytes) -> bool:
        signer_vk_bytes = b58_to_bytes(signer_vk)
        success = ed25519.verify_signed_message(signer_vk_bytes, msg, signature)
        return success

    async def anon_crypt(self, recipient_vk: str, msg: bytes) -> bytes:
        vk_bytes = b58_to_bytes(recipient_vk)
        encrypted = ed25519.crypto_box_seal(msg, vk_bytes)
        return encrypted

    async def anon_decrypt(self, recipient_vk: str, encrypted_msg: bytes) -> bytes:
        await self.__check_verkey_exists(recipient_vk)
        await self.storage.select_db(self.DB_KEYS)
        sk_bytes = await self.storage.get(recipient_vk)
        vk_bytes = b58_to_bytes(recipient_vk)
        decrypt = ed25519.crypto_box_seal_open(vk_bytes, sk_bytes, encrypted_msg)
        return decrypt

    async def pack_message(self, message: Any, recipient_verkeys: list, sender_verkey: str = None) -> bytes:
        if sender_verkey is not None:
            await self.__check_verkey_exists(sender_verkey)
        recipient_verkeys_bytes = []
        for vk_b58 in recipient_verkeys:
            recipient_verkeys_bytes.append(b58_to_bytes(vk_b58))
        sender_verkey_bytes = b58_to_bytes(sender_verkey)
        if sender_verkey is None:
            sender_sigkey_bytes = None
        else:
            await self.storage.select_db(self.DB_KEYS)
            sender_sigkey_bytes = await self.storage.get(sender_verkey)
        jwe = ed25519.pack_message(
            message=message,
            to_verkeys=recipient_verkeys_bytes,
            from_verkey=sender_verkey_bytes,
            from_sigkey=sender_sigkey_bytes
        )
        return jwe

    async def unpack_message(self, jwe: bytes) -> dict:
        try:
            msg = json.loads(jwe.decode())
        except Exception as e:
            if isinstance(e, json.JSONDecodeError) or isinstance(e, UnicodeError):
                raise SiriusCryptoError('Unexpected packed message format')
            else:
                raise
        if 'protected' in msg:
            try:
                recip = base64.b64decode(msg['protected'])
                recip_json = json.loads(recip.decode())
                recipients = recip_json.get('recipients', [])
                my_vk, my_sk = None, None
                await self.storage.select_db(self.DB_KEYS)
                # Search my_key in headers
                for rcp in recipients:
                    header = rcp.get('header', {})
                    vk = header.get('kid', None)
                    if vk is not None:
                        my_sk = await self.storage.get(vk)
                        if my_sk is not None:
                            my_vk = b58_to_bytes(vk)
                            break

                if not my_sk:
                    raise SiriusCryptoError('Unknown key in recipient list')
                unpacked = ed25519.unpack_message(
                    enc_message=jwe, my_verkey=my_vk, my_sigkey=my_sk
                )
                return {
                    'message': unpacked[0],
                    'recipient_verkey': unpacked[2],
                    'sender_verkey': unpacked[1]
                }
            except ValueError:
                raise SiriusCryptoError('Unexpected packed message format')
        else:
            raise SiriusCryptoError('Unexpected packed message format')

    async def __check_verkey_exists(self, verkey: str):
        await self.storage.select_db(self.DB_KEYS)
        sk = await self.storage.get(verkey)
        if sk is None:
            raise SiriusCryptoError(f'Unknown verkey "{verkey}"')
