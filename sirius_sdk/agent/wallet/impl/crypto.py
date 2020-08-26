from typing import Any, Optional

from sirius_sdk.agent.connections import AgentRPC
from sirius_sdk.agent.wallet.abstract.crypto import AbstractCrypto


class CryptoProxy(AbstractCrypto):

    def __init__(self, rpc: AgentRPC):
        self.__rpc = rpc

    async def create_key(self, seed: str = None, crypto_type: str = None) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/create_key',
            params=dict(seed=seed, crypto_type=crypto_type)
        )

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/set_key_metadata',
            params=dict(verkey=verkey, metadata=metadata)
        )

    async def get_key_metadata(self, verkey: str) -> Optional[dict]:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/get_key_metadata',
            params=dict(verkey=verkey)
        )

    async def crypto_sign(self, signer_vk: str, msg: bytes) -> bytes:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/crypto_sign',
            params=dict(signer_vk=signer_vk, msg=msg)
        )

    async def crypto_verify(self, signer_vk: str, msg: bytes, signature: bytes) -> bool:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/crypto_verify',
            params=dict(signer_vk=signer_vk, msg=msg, signature=signature)
        )

    async def anon_crypt(self, recipient_vk: str, msg: bytes) -> bytes:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/anon_crypt',
            params=dict(recipient_vk=recipient_vk, msg=msg)
        )

    async def anon_decrypt(self, recipient_vk: str, encrypted_msg: bytes) -> bytes:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/anon_decrypt',
            params=dict(recipient_vk=recipient_vk, encrypted_msg=encrypted_msg)
        )

    async def pack_message(self, message: Any, recipient_verkeys: list, sender_verkey: str = None) -> bytes:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/pack_message',
            params=dict(message=message, recipient_verkeys=recipient_verkeys, sender_verkey=sender_verkey)
        )

    async def unpack_message(self, jwe: bytes) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/unpack_message',
            params=dict(jwe=jwe)
        )
