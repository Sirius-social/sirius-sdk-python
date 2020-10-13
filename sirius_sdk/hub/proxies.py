from typing import Optional, List, Union, Any

from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.agent.wallet.abstract.crypto import AbstractCrypto
from sirius_sdk.agent.wallet.abstract.did import AbstractDID
from sirius_sdk.agent.pairwise import Pairwise, TheirEndpoint
from sirius_sdk.agent.microledgers import AbstractMicroledgerList, LedgerMeta, Transaction, AbstractMicroledger

from .core import _current_hub


class DIDProxy(AbstractDID):

    async def create_and_store_my_did(self, did: str = None, seed: str = None, cid: bool = None) -> (str, str):
        service = await _current_hub().get_did()
        return await service.create_and_store_my_did(
            did=did, seed=seed, cid=cid
        )

    async def store_their_did(self, did: str, verkey: str = None) -> None:
        service = await _current_hub().get_did()
        return await service.store_their_did(
            did=did, verkey=verkey
        )

    async def set_did_metadata(self, did: str, metadata: dict = None) -> None:
        service = await _current_hub().get_did()
        return await service.set_did_metadata(
            did=did, metadata=metadata
        )

    async def list_my_dids_with_meta(self) -> List[Any]:
        service = await _current_hub().get_did()
        return await service.list_my_dids_with_meta()

    async def get_did_metadata(self, did) -> Optional[dict]:
        service = await _current_hub().get_did()
        return await service.get_did_metadata(did=did)

    async def key_for_local_did(self, did: str) -> str:
        service = await _current_hub().get_did()
        return await service.key_for_local_did(did=did)

    async def key_for_did(self, pool_name: str, did: str) -> str:
        service = await _current_hub().get_did()
        return await service.key_for_did(pool_name=pool_name, did=did)

    async def create_key(self, seed: str = None) -> str:
        service = await _current_hub().get_did()
        return await service.create_key(seed=seed)

    async def replace_keys_start(self, did: str, seed: str = None) -> str:
        service = await _current_hub().get_did()
        return await service.replace_keys_start(did=did, seed=seed)

    async def replace_keys_apply(self, did: str) -> None:
        service = await _current_hub().get_did()
        await service.replace_keys_apply(did=did)

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        service = await _current_hub().get_did()
        await service.set_key_metadata(verkey=verkey, metadata=metadata)

    async def get_key_metadata(self, verkey: str) -> dict:
        service = await _current_hub().get_did()
        return await service.get_key_metadata(verkey=verkey)

    async def set_endpoint_for_did(self, did: str, address: str, transport_key: str) -> None:
        service = await _current_hub().get_did()
        await service.set_endpoint_for_did(did=did, address=address, transport_key=transport_key)

    async def get_endpoint_for_did(self, pool_name: str, did: str) -> (str, Optional[str]):
        service = await _current_hub().get_did()
        return await service.get_endpoint_for_did(pool_name=pool_name, did=did)

    async def get_my_did_with_meta(self, did: str) -> Any:
        service = await _current_hub().get_did()
        return await service.get_my_did_with_meta(did=did)

    async def abbreviate_verkey(self, did: str, full_verkey: str) -> str:
        service = await _current_hub().get_did()
        return await service.abbreviate_verkey(did=did, full_verkey=full_verkey)

    async def qualify_did(self, did: str, method: str) -> str:
        service = await _current_hub().get_did()
        return await service.qualify_did(did=did, method=method)


class CryptoProxy(AbstractCrypto):

    async def create_key(self, seed: str = None, crypto_type: str = None) -> str:
        service = await _current_hub().get_crypto()
        return await service.create_key(seed=seed, crypto_type=crypto_type)

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        service = await _current_hub().get_crypto()
        return await service.set_key_metadata(verkey=verkey, metadata=metadata)

    async def get_key_metadata(self, verkey: str) -> Optional[dict]:
        service = await _current_hub().get_crypto()
        return await service.get_key_metadata(verkey=verkey)

    async def crypto_sign(self, signer_vk: str, msg: bytes) -> bytes:
        service = await _current_hub().get_crypto()
        return await service.crypto_sign(signer_vk=signer_vk, msg=msg)

    async def crypto_verify(self, signer_vk: str, msg: bytes, signature: bytes) -> bool:
        service = await _current_hub().get_crypto()
        return await service.crypto_verify(signer_vk=signer_vk, msg=msg, signature=signature)

    async def anon_crypt(self, recipient_vk: str, msg: bytes) -> bytes:
        service = await _current_hub().get_crypto()
        return await service.anon_crypt(recipient_vk=recipient_vk, msg=msg)

    async def anon_decrypt(self, recipient_vk: str, encrypted_msg: bytes) -> bytes:
        service = await _current_hub().get_crypto()
        return await service.anon_decrypt(recipient_vk=recipient_vk, encrypted_msg=encrypted_msg)

    async def pack_message(self, message: Any, recipient_verkeys: list, sender_verkey: str = None) -> bytes:
        service = await _current_hub().get_crypto()
        return await service.pack_message(
            message=message, recipient_verkeys=recipient_verkeys, sender_verkey=sender_verkey
        )

    async def unpack_message(self, jwe: bytes) -> dict:
        service = await _current_hub().get_crypto()
        return await service.unpack_message(jwe=jwe)


class MicroledgersProxy(AbstractMicroledgerList):

    async def create(
            self, name: str, genesis: Union[List[Transaction], List[dict]]
    ) -> (AbstractMicroledger, List[Transaction]):
        service = await _current_hub().get_microledgers()
        return await service.create(name, genesis)

    async def ledger(self, name: str) -> AbstractMicroledger:
        service = await _current_hub().get_microledgers()
        return await service.ledger(name)

    async def reset(self, name: str):
        service = await _current_hub().get_microledgers()
        await service.reset(name)

    async def is_exists(self, name: str):
        service = await _current_hub().get_microledgers()
        return await service.is_exists(name)

    async def leaf_hash(self, txn: Union[Transaction, bytes]) -> bytes:
        service = await _current_hub().get_microledgers()
        return await service.leaf_hash(txn)

    async def list(self) -> List[LedgerMeta]:
        service = await _current_hub().get_microledgers()
        return await service.list()


class PairwiseProxy(AbstractPairwiseList):

    async def create(self, pairwise: Pairwise):
        service = await _current_hub().get_pairwise_list()
        await service.create(pairwise)

    async def update(self, pairwise: Pairwise):
        service = await _current_hub().get_pairwise_list()
        await service.update(pairwise)

    async def is_exists(self, their_did: str) -> bool:
        service = await _current_hub().get_pairwise_list()
        return await service.is_exists(their_did)

    async def ensure_exists(self, pairwise: Pairwise):
        service = await _current_hub().get_pairwise_list()
        await service.ensure_exists(pairwise)

    async def load_for_did(self, their_did: str) -> Optional[Pairwise]:
        service = await _current_hub().get_pairwise_list()
        return await service.load_for_did(their_did)

    async def load_for_verkey(self, their_verkey: str) -> Optional[Pairwise]:
        service = await _current_hub().get_pairwise_list()
        return await service.load_for_verkey(their_verkey)
