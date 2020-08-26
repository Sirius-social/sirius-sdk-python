from typing import Optional, Any, List

from sirius_sdk.agent.wallet import NYMRole
from sirius_sdk.agent.wallet.abstract.ledger import AbstractLedger
from sirius_sdk.agent.connections import AgentRPC


class LedgerProxy(AbstractLedger):

    def __init__(self, rpc: AgentRPC):
        self.__rpc = rpc

    async def read_nym(self, pool_name: str, submitter_did: Optional[str], target_did: str) -> (bool, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/read_nym',
            params=dict(pool_name=pool_name, submitter_did=submitter_did, target_did=target_did)
        )

    async def read_attribute(
            self, pool_name: str, submitter_did: Optional[str], target_did: str, name: str
    ) -> (bool, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/read_attribute',
            params=dict(pool_name=pool_name, submitter_did=submitter_did, target_did=target_did, name=name)
        )

    async def write_nym(
            self, pool_name: str, submitter_did: str, target_did: str,
            ver_key: str = None, alias: str = None, role: NYMRole = None
    ) -> (bool, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/write_nym',
            params=dict(
                pool_name=pool_name, submitter_did=submitter_did,
                target_did=target_did, ver_key=ver_key, alias=alias, role=role
            )
        )

    async def register_schema(self, pool_name: str, submitter_did: str, data: dict) -> (bool, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/register_schema',
            params=dict(pool_name=pool_name, submitter_did=submitter_did, data=data)
        )

    async def register_cred_def(self, pool_name: str, submitter_did: str, data: dict) -> (bool, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/register_cred_def',
            params=dict(pool_name=pool_name, submitter_did=submitter_did, data=data)
        )

    async def write_attribute(
            self, pool_name: str, submitter_did: Optional[str], target_did: str, name: str, value: Any
    ) -> (bool, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/write_attribute',
            params=dict(pool_name=pool_name, submitter_did=submitter_did, target_did=target_did, name=name, value=value)
        )

    async def sign_and_submit_request(self, pool_name: str, submitter_did: str, request: dict) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/sign_and_submit_request',
            params=dict(pool_name=pool_name, submitter_did=submitter_did, request=request)
        )

    async def submit_request(self, pool_name: str, request: dict) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/admin/1.0/submit_request',
            params=dict(pool_name=pool_name, request=request)
        )

    async def submit_action(self, pool_name: str, request: dict, nodes: List[str] = None, timeout: int = None) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/submit_action',
            params=dict(pool_name=pool_name, request=request, nodes=nodes, timeout=timeout)
        )

    async def sign_request(self, submitter_did: str, request: dict) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/sign_request',
            params=dict(submitter_did=submitter_did, request=request)
        )

    async def multi_sign_request(self, submitter_did: str, request: dict) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/multi_sign_request',
            params=dict(submitter_did=submitter_did, request=request)
        )

    async def build_get_ddo_request(self, submitter_did: Optional[str], target_did: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_ddo_request',
            params=dict(submitter_did=submitter_did, target_did=target_did)
        )

    async def build_nym_request(
            self, submitter_did: str, target_did: str, ver_key: str = None, alias: str = None, role: NYMRole = None
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_nym_request',
            params=dict(
                submitter_did=submitter_did, target_did=target_did,
                ver_key=ver_key, alias=alias, role=role
            )
        )

    async def build_attrib_request(
            self, submitter_did: str, target_did: str, xhash: str = None, raw: dict = None, enc: str = None
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_attrib_request',
            params=dict(
                submitter_did=submitter_did,
                target_did=target_did, xhash=xhash, raw=raw, enc=enc
            )
        )

    async def build_get_attrib_request(
            self, submitter_did: Optional[str], target_did: str, raw: str = None, xhash: str = None, enc: str = None
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_attrib_request',
            params=dict(submitter_did=submitter_did, target_did=target_did, raw=raw, xhash=xhash, enc=enc)
        )

    async def build_get_nym_request(self, submitter_did: Optional[str], target_did: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_nym_request',
            params=dict(submitter_did=submitter_did, target_did=target_did)
        )

    async def parse_get_nym_response(self, response: Any) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/parse_get_nym_response',
            params=dict(response=response)
        )

    async def build_schema_request(self, submitter_did: str, data: dict) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_schema_request',
            params=dict(submitter_did=submitter_did, data=data)
        )

    async def build_get_schema_request(self, submitter_did: Optional[str], id_: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_schema_request',
            params=dict(submitter_did=submitter_did, id_=id_)
        )

    async def parse_get_schema_response(self, get_schema_response: dict) -> (str, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/parse_get_schema_response',
            params=dict(get_schema_response=get_schema_response)
        )

    async def build_cred_def_request(self, submitter_did: str, data: dict) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/admin/1.0/build_cred_def_request',
            params=dict(submitter_did=submitter_did, data=data)
        )

    async def build_get_cred_def_request(self, submitter_did: Optional[str], id_: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_cred_def_request',
            params=dict(submitter_did=submitter_did, id_=id_)
        )

    async def parse_get_cred_def_response(self, get_cred_def_response: dict) -> (str, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/parse_get_cred_def_response',
            params=dict(get_cred_def_response=get_cred_def_response)
        )

    async def build_node_request(self, submitter_did: str, target_did: str, data: dict) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_node_request',
            params=dict(submitter_did=submitter_did, target_did=target_did, data=data)
        )

    async def build_get_validator_info_request(self, submitter_did: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_validator_info_request',
            params=dict(submitter_did=submitter_did)
        )

    async def build_get_txn_request(
            self, submitter_did: Optional[str], ledger_type: Optional[str], seq_no: int
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_txn_request',
            params=dict(submitter_did=submitter_did, ledger_type=ledger_type, seq_no=seq_no)
        )

    async def build_pool_config_request(self, submitter_did: str, writes: bool, force: bool) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_pool_config_request',
            params=dict(submitter_did=submitter_did, writes=writes, force=force)
        )

    async def build_pool_restart_request(self, submitter_did: str, action: str, datetime: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_pool_restart_request',
            params=dict(submitter_did=submitter_did, action=action, datetime=datetime)
        )

    async def build_pool_upgrade_request(
            self, submitter_did: str, name: str, version: str, action: str, _sha256: str,
            _timeout: Optional[int], schedule: Optional[str], justification: Optional[str],
            reinstall: bool, force: bool, package: Optional[str]
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_pool_upgrade_request',
            params=dict(
                submitter_did=submitter_did, name=name, version=version, action=action,
                _sha256=_sha256, _timeout=_timeout, schedule=schedule, justification=justification,
                reinstall=reinstall, force=force, package=package
            )
        )

    async def build_revoc_reg_def_request(self, submitter_did: str, data: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_revoc_reg_def_request',
            params=dict(submitter_did=submitter_did, data=data)
        )

    async def build_get_revoc_reg_def_request(
            self, submitter_did: Optional[str], rev_reg_def_id: str
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_revoc_reg_def_request',
            params=dict(submitter_did=submitter_did, rev_reg_def_id=rev_reg_def_id)
        )

    async def parse_get_revoc_reg_def_response(self, get_revoc_ref_def_response: dict) -> (str, dict):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/parse_get_revoc_reg_def_response',
            params=dict(get_revoc_ref_def_response=get_revoc_ref_def_response)
        )

    async def build_revoc_reg_entry_request(
            self, submitter_did: str, revoc_reg_def_id: str, rev_def_type: str, value: dict
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_revoc_reg_entry_request',
            params=dict(
                submitter_did=submitter_did, revoc_reg_def_id=revoc_reg_def_id, rev_def_type=rev_def_type, value=value
            )
        )

    async def build_get_revoc_reg_request(
            self, submitter_did: Optional[str], revoc_reg_def_id: str, timestamp: int
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_revoc_reg_request',
            params=dict(submitter_did=submitter_did, revoc_reg_def_id=revoc_reg_def_id, timestamp=timestamp)
        )

    async def parse_get_revoc_reg_response(self, get_revoc_reg_response: dict) -> (str, dict, int):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/parse_get_revoc_reg_response',
            params=dict(get_revoc_reg_response=get_revoc_reg_response)
        )

    async def build_get_revoc_reg_delta_request(
            self, submitter_did: Optional[str], revoc_reg_def_id: str,
            from_: Optional[int], to: int
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_revoc_reg_delta_request',
            params=dict(
                submitter_did=submitter_did, revoc_reg_def_id=revoc_reg_def_id, from_=from_, to=to
            )
        )

    async def parse_get_revoc_reg_delta_response(self, get_revoc_reg_delta_response: dict) -> (str, dict, int):
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/parse_get_revoc_reg_delta_response',
            params=dict(get_revoc_reg_delta_response=get_revoc_reg_delta_response)
        )

    async def get_response_metadata(self, response: dict) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/get_response_metadata',
            params=dict(response=response)
        )

    async def build_auth_rule_request(
            self, submitter_did: str, txn_type: str, action: str, field: str,
            old_value: Optional[str], new_value: Optional[str], constraint: dict
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_auth_rule_request',
            params=dict(
                submitter_did=submitter_did, txn_type=txn_type, action=action, field=field,
                old_value=old_value, new_value=new_value, constraint=constraint
            )
        )

    async def build_auth_rules_request(self, submitter_did: str, data: dict) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_auth_rules_request',
            params=dict(submitter_did=submitter_did, data=data)
        )

    async def build_get_auth_rule_request(
            self, submitter_did: Optional[str], txn_type: Optional[str],
            action: Optional[str], field: Optional[str], old_value: Optional[str], new_value: Optional[str]
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_auth_rule_request',
            params=dict(
                submitter_did=submitter_did, txn_type=txn_type, action=action,
                field=field, old_value=old_value, new_value=new_value
            )
        )

    async def build_txn_author_agreement_request(
            self, submitter_did: str, text: Optional[str],
            version: str, ratification_ts: Optional[int] = None, retirement_ts: Optional[int] = None
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_txn_author_agreement_request',
            params=dict(
                submitter_did=submitter_did, text=text, version=version,
                ratification_ts=ratification_ts, retirement_ts=retirement_ts
            )
        )

    async def build_disable_all_txn_author_agreements_request(self, submitter_did: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_disable_all_txn_author_agreements_request',
            params=dict(submitter_did=submitter_did)
        )

    async def build_get_txn_author_agreement_request(self, submitter_did: Optional[str], data: dict = None) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_txn_author_agreement_request',
            params=dict(submitter_did=submitter_did, data=data)
        )

    async def build_acceptance_mechanisms_request(
            self, submitter_did: str, aml: dict, version: str, aml_context: Optional[str]
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_acceptance_mechanisms_request',
            params=dict(submitter_did=submitter_did, aml=aml, version=version, aml_context=aml_context)
        )

    async def build_get_acceptance_mechanisms_request(
            self, submitter_did: Optional[str], timestamp: Optional[int], version: Optional[str]
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/build_get_acceptance_mechanisms_request',
            params=dict(submitter_did=submitter_did, timestamp=timestamp, version=version)
        )

    async def append_txn_author_agreement_acceptance_to_request(
            self, request: dict, text: Optional[str],
            version: Optional[str], taa_digest: Optional[str], mechanism: str, time: int
    ) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/append_txn_author_agreement_acceptance_to_request',
            params=dict(
                request=request, text=text, version=version,
                taa_digest=taa_digest, mechanism=mechanism, time=time
            )
        )

    async def append_request_endorser(self, request: dict, endorser_did: str) -> dict:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/append_request_endorser',
            params=dict(request=request, endorser_did=endorser_did)
        )
