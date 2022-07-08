import base64
from typing import Any, Optional, Dict

from sirius_sdk.abstract.api import APICrypto
from sirius_sdk.encryption.ed25519 import *


class InMemoryCrypto(APICrypto):

    def __init__(self):
        self.__keys_metadata: Dict[str, dict] = {}
        self.__pk_2_sk: Dict[str, bytes] = {}

    async def create_key(self, seed: str = None, crypto_type: str = None) -> str:
        pk_bytes, sk_bytes = create_keypair(seed.encode() if seed else None)
        pk_b58 = bytes_to_b58(pk_bytes)
        self.__pk_2_sk[pk_b58] = sk_bytes
        return pk_b58

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        self.__check_verkey_exists(verkey)
        self.__keys_metadata[verkey] = metadata

    async def get_key_metadata(self, verkey: str) -> Optional[dict]:
        self.__check_verkey_exists(verkey)
        return self.__keys_metadata.get(verkey, None)

    async def crypto_sign(self, signer_vk: str, msg: bytes) -> bytes:
        sk_bytes = self.__pk_2_sk.get(signer_vk, None)
        signed = sign_message(msg, sk_bytes)
        return signed

    async def crypto_verify(self, signer_vk: str, msg: bytes, signature: bytes) -> bool:
        signer_vk_bytes = b58_to_bytes(signer_vk)
        success = verify_signed_message(signer_vk_bytes, msg, signature)
        return success

    async def anon_crypt(self, recipient_vk: str, msg: bytes) -> bytes:
        vk_bytes = b58_to_bytes(recipient_vk)
        encrypted = crypto_box_seal(msg, vk_bytes)
        return encrypted

    async def anon_decrypt(self, recipient_vk: str, encrypted_msg: bytes) -> bytes:
        self.__check_verkey_exists(recipient_vk)
        sk_bytes = self.__pk_2_sk[recipient_vk]
        vk_bytes = b58_to_bytes(recipient_vk)
        decrypt = crypto_box_seal_open(vk_bytes, sk_bytes, encrypted_msg)
        return decrypt

    async def pack_message(self, message: Any, recipient_verkeys: list, sender_verkey: str = None) -> bytes:
        if sender_verkey is not None:
            self.__check_verkey_exists(sender_verkey)
        recipient_verkeys_bytes = []
        for vk_b58 in recipient_verkeys:
            recipient_verkeys_bytes.append(b58_to_bytes(vk_b58))
        sender_verkey_bytes = b58_to_bytes(sender_verkey)
        if sender_verkey is None:
            sender_sigkey_bytes = None
        else:
            sender_sigkey_bytes = self.__pk_2_sk.get(sender_verkey, None)
            if sender_sigkey_bytes is None:
                raise SiriusCryptoError(f'Unknown sigkey for verkey "{sender_verkey}"')
        jwe = pack_message(
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
                for rcp in recipients:
                    header = rcp.get('header', {})
                    vk = header.get('kid', None)
                    if vk is not None and vk in self.__pk_2_sk.keys():
                        my_vk, my_sk = b58_to_bytes(vk), self.__pk_2_sk[vk]
                        break
                if not my_sk:
                    raise SiriusCryptoError('Unknown key in recipient list')
                unpacked = unpack_message(
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

    def __check_verkey_exists(self, verkey: str):
        if verkey not in self.__pk_2_sk.keys():
            raise SiriusCryptoError(f'Unknown verkey "{verkey}"')
