from typing import List, Optional

from sirius_sdk.agent.wallet.abstract.anoncreds import AbstractAnonCreds, AnonCredSchema
from sirius_sdk.agent.connections import AgentRPC


class AnonCredsProxy(AbstractAnonCreds):

    def __init__(self, rpc: AgentRPC):
        self.__rpc = rpc

    async def issuer_create_schema(
            self, issuer_did: str, name: str, version: str, attrs: List[str]
    ) -> (str, AnonCredSchema):
        schema_id, body = await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/issuer_create_schema',
            params=dict(issuer_did=issuer_did, name=name, version=version, attrs=attrs)
        )
        return schema_id, AnonCredSchema(**body)

    async def issuer_create_and_store_credential_def(
            self, issuer_did: str, schema: dict, tag: str, signature_type: str = None, config: dict = None
    ) -> (str, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/issuer_create_and_store_credential_def',
            params=dict(issuer_did=issuer_did, schema=schema, tag=tag, signature_type=signature_type, config=config)
        )

    async def issuer_rotate_credential_def_start(self, cred_def_id: str, config: dict = None) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/issuer_rotate_credential_def_start',
            params=dict(cred_def_id=cred_def_id, config=config)
        )

    async def issuer_rotate_credential_def_apply(self, cred_def_id: str):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/issuer_rotate_credential_def_apply',
            params=dict(cred_def_id=cred_def_id)
        )

    async def issuer_create_and_store_revoc_reg(
            self, issuer_did: str, revoc_def_type: Optional[str], tag: str,
            cred_def_id: str, config: dict, tails_writer_handle: int
    ) -> (str, dict, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/issuer_create_and_store_revoc_reg',
            params=dict(
                issuer_did=issuer_did, revoc_def_type=revoc_def_type, tag=tag,
                cred_def_id=cred_def_id, config=config, tails_writer_handle=tails_writer_handle
            )
        )

    async def issuer_create_credential_offer(self, cred_def_id: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/issuer_create_credential_offer',
            params=dict(cred_def_id=cred_def_id)
        )

    async def issuer_create_credential(
            self, cred_offer: dict, cred_req: dict, cred_values: dict,
            rev_reg_id: str = None, blob_storage_reader_handle: int = None
    ) -> (dict, Optional[str], Optional[dict]):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/issuer_create_credential',
            params=dict(
                cred_offer=cred_offer, cred_req=cred_req, cred_values=cred_values,
                rev_reg_id=rev_reg_id, blob_storage_reader_handle=blob_storage_reader_handle
            )
        )

    async def issuer_revoke_credential(
            self, blob_storage_reader_handle: int, rev_reg_id: str, cred_revoc_id: str
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/issuer_revoke_credential',
            params=dict(
                blob_storage_reader_handle=blob_storage_reader_handle,
                rev_reg_id=rev_reg_id, cred_revoc_id=cred_revoc_id
            )
        )

    async def issuer_merge_revocation_registry_deltas(self, rev_reg_delta: dict, other_rev_reg_delta: dict) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/issuer_merge_revocation_registry_deltas',
            params=dict(rev_reg_delta=rev_reg_delta, other_rev_reg_delta=other_rev_reg_delta)
        )

    async def prover_create_master_secret(self, master_secret_name: str = None) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_create_master_secret',
            params=dict(master_secret_name=master_secret_name)
        )

    async def prover_create_credential_req(
            self, prover_did: str, cred_offer: dict, cred_def: dict, master_secret_id: str
    ) -> (dict, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_create_credential_req',
            params=dict(
                prover_did=prover_did, cred_offer=cred_offer, cred_def=cred_def, master_secret_id=master_secret_id
            )
        )

    async def prover_set_credential_attr_tag_policy(
            self, cred_def_id: str, tag_attrs: Optional[dict], retroactive: bool
    ) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_set_credential_attr_tag_policy',
            params=dict(cred_def_id=cred_def_id, tag_attrs=tag_attrs, retroactive=retroactive)
        )

    async def prover_get_credential_attr_tag_policy(self, cred_def_id: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_get_credential_attr_tag_policy',
            params=dict(cred_def_id=cred_def_id)
        )

    async def prover_store_credential(
            self, cred_id: Optional[str], cred_req_metadata: dict, cred: dict, cred_def: dict, rev_reg_def: dict = None
    ) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_store_credential',
            params=dict(
                cred_id=cred_id, cred_req_metadata=cred_req_metadata,
                cred=cred, cred_def=cred_def, rev_reg_def=rev_reg_def
            )
        )

    async def prover_get_credential(self, cred_id: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_get_credential',
            params=dict(cred_id=cred_id)
        )

    async def prover_delete_credential(self, cred_id: str) -> None:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_delete_credential',
            params=dict(cred_id=cred_id)
        )

    async def prover_get_credentials(self, filters: dict) -> List[dict]:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_get_credentials',
            params=dict(filters=filters)
        )

    async def prover_search_credentials(self, query: dict) -> List[dict]:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_search_credentials',
            params=dict(query=query)
        )

    async def prover_get_credentials_for_proof_req(self, proof_request: dict) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_get_credentials_for_proof_req',
            params=dict(proof_request=proof_request)
        )

    async def prover_search_credentials_for_proof_req(
            self, proof_request: dict, extra_query: dict = None, limit_referents: int = 1
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_search_credentials_for_proof_req',
            params=dict(
                proof_request=proof_request, extra_query=extra_query, limit_referents=limit_referents
            )
        )

    async def prover_create_proof(
            self, proof_req: dict, requested_credentials: dict, master_secret_name: str,
            schemas: dict, credential_defs: dict, rev_states: dict
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prover_create_proof',
            params=dict(
                proof_req=proof_req, requested_credentials=requested_credentials,
                master_secret_name=master_secret_name, schemas=schemas,
                credential_defs=credential_defs, rev_states=rev_states
            )
        )

    async def verifier_verify_proof(
            self, proof_request: dict, proof: dict, schemas: dict,
            credential_defs: dict, rev_reg_defs: dict, rev_regs: dict
    ) -> bool:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/verifier_verify_proof',
            params=dict(
                proof_request=proof_request, proof=proof, schemas=schemas,
                credential_defs=credential_defs, rev_reg_defs=rev_reg_defs, rev_regs=rev_regs
            )
        )

    async def create_revocation_state(
            self, blob_storage_reader_handle: int, rev_reg_def: dict,
            rev_reg_delta: dict, timestamp: int, cred_rev_id: str
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/create_revocation_state',
            params=dict(
                blob_storage_reader_handle=blob_storage_reader_handle, rev_reg_def=rev_reg_def,
                rev_reg_delta=rev_reg_delta, timestamp=timestamp, cred_rev_id=cred_rev_id
            )
        )

    async def update_revocation_state(
            self, blob_storage_reader_handle: int, rev_state: dict, rev_reg_def: dict,
            rev_reg_delta: dict, timestamp: int, cred_rev_id: str
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/update_revocation_state',
            params=dict(
                blob_storage_reader_handle=blob_storage_reader_handle, rev_state=rev_state,
                rev_reg_def=rev_reg_def, rev_reg_delta=rev_reg_delta, timestamp=timestamp, cred_rev_id=cred_rev_id
            )
        )

    async def generate_nonce(self) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/generate_nonce'
        )

    async def to_unqualified(self, entity: str) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/to_unqualified',
            params=dict(entity=entity)
        )
