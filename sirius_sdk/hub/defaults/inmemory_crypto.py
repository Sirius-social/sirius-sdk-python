from typing import Any, Optional, Dict

from sirius_sdk.abstract.api import APICrypto
from sirius_sdk.encryption.ed25519 import *


class InMemoryCrypto(APICrypto):

    def __init__(self):
        self.__keys_metadata: Dict[str, dict] = {}
        self.__pk_2_sk: Dict[str, bytes] = {}

    async def create_key(self, seed: str = None, crypto_type: str = None) -> str:
        pk_bytes, sk_bytes = await create_keypair(seed.encode())
        pk_b58 = bytes_to_b58(pk_bytes)
        self.__pk_2_sk[pk_b58] = sk_bytes
        return pk_b58

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        self.__keys_metadata[verkey] = metadata

    async def get_key_metadata(self, verkey: str) -> Optional[dict]:
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
        pass

    async def anon_decrypt(self, recipient_vk: str, encrypted_msg: bytes) -> bytes:
        pass

    async def pack_message(self, message: Any, recipient_verkeys: list, sender_verkey: str = None) -> bytes:
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
        message, sender_vk, recip_vk = unpack_message(

        )
