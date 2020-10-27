from typing import Optional, List, Union, Any

from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.agent.wallet.abstract.crypto import AbstractCrypto
from sirius_sdk.agent.wallet.abstract.cache import AbstractCache
from sirius_sdk.agent.wallet.abstract.did import AbstractDID
from sirius_sdk.agent.wallet.abstract.anoncreds import AbstractAnonCreds
from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.agent.microledgers import AbstractMicroledgerList, LedgerMeta, Transaction, AbstractMicroledger

from .core import _current_hub
from ..agent.wallet import PurgeOptions, CacheOptions
from ..agent.wallet.abstract import AnonCredSchema


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


class AnonCredsProxy(AbstractAnonCreds):

    async def issuer_create_schema(
            self, issuer_did: str, name: str, version: str, attrs: List[str]
    ) -> (str, AnonCredSchema):
        service = await _current_hub().get_anoncreds()
        return await service.issuer_create_schema(
            issuer_did=issuer_did, name=name,
            version=version, attrs=attrs
        )

    async def issuer_create_and_store_credential_def(
            self, issuer_did: str, schema: dict, tag: str, signature_type: str = None, config: dict = None
    ) -> (str, dict):
        service = await _current_hub().get_anoncreds()
        return await service.issuer_create_and_store_credential_def(
            issuer_did=issuer_did, schema=schema, tag=tag, signature_type=signature_type, config=config
        )

    async def issuer_rotate_credential_def_start(self, cred_def_id: str, config: dict = None) -> dict:
        service = await _current_hub().get_anoncreds()
        return await service.issuer_rotate_credential_def_start(
            cred_def_id=cred_def_id, config=config
        )

    async def issuer_rotate_credential_def_apply(self, cred_def_id: str):
        service = await _current_hub().get_anoncreds()
        await service.issuer_rotate_credential_def_apply(
            cred_def_id=cred_def_id
        )

    async def issuer_create_and_store_revoc_reg(
            self, issuer_did: str, revoc_def_type: Optional[str],
            tag: str, cred_def_id: str, config: dict, tails_writer_handle: int
    ) -> (str, dict, dict):
        service = await _current_hub().get_anoncreds()
        return await service.issuer_create_and_store_revoc_reg(
            issuer_did=issuer_did, revoc_def_type=revoc_def_type,
            tag=tag, cred_def_id=cred_def_id, config=config, tails_writer_handle=tails_writer_handle
        )

    async def issuer_create_credential_offer(self, cred_def_id: str) -> dict:
        service = await _current_hub().get_anoncreds()
        return await service.issuer_create_credential_offer(cred_def_id=cred_def_id)

    async def issuer_create_credential(
            self, cred_offer: dict, cred_req: dict, cred_values: dict,
            rev_reg_id: str = None, blob_storage_reader_handle: int = None
    ) -> (dict, Optional[str], Optional[dict]):
        service = await _current_hub().get_anoncreds()
        return await service.issuer_create_credential(
            cred_offer=cred_offer, cred_req=cred_req, cred_values=cred_values,
            rev_reg_id=rev_reg_id, blob_storage_reader_handle=blob_storage_reader_handle
        )

    async def issuer_revoke_credential(
            self, blob_storage_reader_handle: int, rev_reg_id: str, cred_revoc_id: str
    ) -> dict:
        service = await _current_hub().get_anoncreds()
        return await service.issuer_revoke_credential(
            blob_storage_reader_handle=blob_storage_reader_handle, rev_reg_id=rev_reg_id, cred_revoc_id=cred_revoc_id
        )

    async def issuer_merge_revocation_registry_deltas(self, rev_reg_delta: dict, other_rev_reg_delta: dict) -> dict:
        service = await _current_hub().get_anoncreds()
        return await service.issuer_merge_revocation_registry_deltas(
            rev_reg_delta=rev_reg_delta, other_rev_reg_delta=other_rev_reg_delta
        )

    async def prover_create_master_secret(self, master_secret_name: str = None) -> str:
        service = await _current_hub().get_anoncreds()
        return await service.prover_create_master_secret(
            master_secret_name=master_secret_name
        )

    async def prover_create_credential_req(
            self, prover_did: str, cred_offer: dict, cred_def: dict, master_secret_id: str
    ) -> (dict, dict):
        service = await _current_hub().get_anoncreds()
        return await service.prover_create_credential_req(
            prover_did=prover_did, cred_offer=cred_offer, cred_def=cred_def, master_secret_id=master_secret_id
        )

    async def prover_set_credential_attr_tag_policy(
            self, cred_def_id: str, tag_attrs: Optional[dict], retroactive: bool
    ) -> None:
        service = await _current_hub().get_anoncreds()
        await service.prover_set_credential_attr_tag_policy(
            cred_def_id=cred_def_id, tag_attrs=tag_attrs, retroactive=retroactive
        )

    async def prover_get_credential_attr_tag_policy(self, cred_def_id: str) -> dict:
        service = await _current_hub().get_anoncreds()
        return await service.prover_get_credential_attr_tag_policy(
            cred_def_id=cred_def_id
        )

    async def prover_store_credential(
            self, cred_id: Optional[str], cred_req_metadata: dict, cred: dict, cred_def: dict, rev_reg_def: dict = None
    ) -> str:
        service = await _current_hub().get_anoncreds()
        return await service.prover_store_credential(
            cred_id=cred_id, cred_req_metadata=cred_req_metadata, cred=cred,
            cred_def=cred_def, rev_reg_def=rev_reg_def
        )

    async def prover_get_credential(self, cred_id: str) -> dict:
        service = await _current_hub().get_anoncreds()
        return await service.prover_get_credential(cred_id=cred_id)

    async def prover_delete_credential(self, cred_id: str) -> None:
        service = await _current_hub().get_anoncreds()
        await service.prover_delete_credential(cred_id=cred_id)

    async def prover_get_credentials(self, filters: dict) -> List[dict]:
        service = await _current_hub().get_anoncreds()
        return await service.prover_get_credentials(filters=filters)

    async def prover_search_credentials(self, query: dict) -> List[dict]:
        service = await _current_hub().get_anoncreds()
        return await service.prover_search_credentials(query=query)

    async def prover_get_credentials_for_proof_req(self, proof_request: dict) -> dict:
        service = await _current_hub().get_anoncreds()
        return await service.prover_get_credentials_for_proof_req(proof_request=proof_request)

    async def prover_search_credentials_for_proof_req(
            self, proof_request: dict, extra_query: dict = None, limit_referents: int = 1
    ) -> dict:
        service = await _current_hub().get_anoncreds()
        return await service.prover_search_credentials_for_proof_req(
            proof_request=proof_request, extra_query=extra_query, limit_referents=limit_referents
        )

    async def prover_create_proof(
            self, proof_req: dict, requested_credentials: dict,
            master_secret_name: str, schemas: dict, credential_defs: dict, rev_states: dict
    ) -> dict:
        service = await _current_hub().get_anoncreds()
        return await service.prover_create_proof(
            proof_req=proof_req, requested_credentials=requested_credentials,
            master_secret_name=master_secret_name, schemas=schemas,
            credential_defs=credential_defs, rev_states=rev_states
        )

    async def verifier_verify_proof(
            self, proof_request: dict, proof: dict, schemas: dict,
            credential_defs: dict, rev_reg_defs: dict, rev_regs: dict
    ) -> bool:
        service = await _current_hub().get_anoncreds()
        return await service.verifier_verify_proof(
            proof_request=proof_request, proof=proof,
            schemas=schemas, credential_defs=credential_defs,
            rev_reg_defs=rev_reg_defs, rev_regs=rev_regs
        )

    async def create_revocation_state(
            self, blob_storage_reader_handle: int, rev_reg_def: dict,
            rev_reg_delta: dict, timestamp: int, cred_rev_id: str
    ) -> dict:
        service = await _current_hub().get_anoncreds()
        return await service.create_revocation_state(
            blob_storage_reader_handle=blob_storage_reader_handle, rev_reg_def=rev_reg_def,
            rev_reg_delta=rev_reg_delta, timestamp=timestamp, cred_rev_id=cred_rev_id
        )

    async def update_revocation_state(
            self, blob_storage_reader_handle: int, rev_state: dict,
            rev_reg_def: dict, rev_reg_delta: dict, timestamp: int, cred_rev_id: str
    ) -> dict:
        service = await _current_hub().get_anoncreds()
        return await service.update_revocation_state(
            blob_storage_reader_handle=blob_storage_reader_handle, rev_state=rev_state,
            rev_reg_def=rev_reg_def, rev_reg_delta=rev_reg_delta, timestamp=timestamp, cred_rev_id=cred_rev_id
        )

    async def generate_nonce(self) -> str:
        service = await _current_hub().get_anoncreds()
        return await service.generate_nonce()

    async def to_unqualified(self, entity: str) -> str:
        service = await _current_hub().get_anoncreds()
        return await service.to_unqualified(entity=entity)


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

    async def _start_loading(self):
        service = await _current_hub().get_pairwise_list()
        await service._start_loading()

    async def _partial_load(self) -> (bool, List[Pairwise]):
        service = await _current_hub().get_pairwise_list()
        return await service._partial_load()

    async def _stop_loading(self):
        service = await _current_hub().get_pairwise_list()
        await service._stop_loading()


class CacheProxy(AbstractCache):

    async def get_schema(self, pool_name: str, submitter_did: str, id_: str, options: CacheOptions) -> dict:
        service = await _current_hub().get_cache()
        return await service.get_schema(
            pool_name=pool_name, submitter_did=submitter_did, id_=id_, options=options
        )

    async def get_cred_def(self, pool_name: str, submitter_did: str, id_: str, options: CacheOptions) -> dict:
        service = await _current_hub().get_cache()
        return await service.get_cred_def(
            pool_name=pool_name,
            submitter_did=submitter_did,
            id_=id_, options=options
        )

    async def purge_schema_cache(self, options: PurgeOptions) -> None:
        service = await _current_hub().get_cache()
        await service.purge_schema_cache(options=options)

    async def purge_cred_def_cache(self, options: PurgeOptions) -> None:
        service = await _current_hub().get_cache()
        await service.purge_cred_def_cache(options=options)
