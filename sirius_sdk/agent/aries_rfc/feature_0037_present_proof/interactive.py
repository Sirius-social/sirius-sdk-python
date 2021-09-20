from typing import Callable, Any, Dict, List, Optional

import sirius_sdk
from sirius_sdk.hub import AbstractP2PCoProtocol
from sirius_sdk.agent.wallet.abstract.cache import CacheOptions
from sirius_sdk.agent.aries_rfc.feature_0015_acks import Ack
from sirius_sdk.agent.aries_rfc.feature_0037_present_proof.error_codes import *
from sirius_sdk.agent.aries_rfc.feature_0037_present_proof.messages import *


class SelfIdentity:
    """Wallet may contains multiple variants if attrib set to resolve proof_request
        it is tool to make decision
    """

    class SelfAttestedAttribute:
        """Self attested attribute
        """

        def __init__(self, referent_id: str, name: str, value: Any):
            self.value = value
            self.__referent_id = referent_id
            self.__name = name

        @property
        def name(self) -> str:
            return self.__name

        @property
        def referent_id(self) -> str:
            return self.__referent_id

    class CredAttribute:
        """Credential info of candidate attribute
        """
        def __init__(
                self, uid: str, cred_info: dict, revealed: bool,
                attr_name: str, on_select: Callable = None
        ):
            """
            :param cred_info: retrieved metadata from prover_search_credentials_for_proof_req wallet call
            :param revealed: make attrib revealed or No
            :param on_select(instance): callback to handle attribute was selected
            """
            self.uid = uid
            self.revealed = revealed
            self.__selected = False
            self.__cred_info = cred_info
            self.__on_select = on_select
            self.__attr_name = attr_name

        @property
        def is_selected(self) -> bool:
            """Attribute was selected in proving interaction"""
            return self.__selected

        @is_selected.setter
        def is_selected(self, value: bool):
            if self.__selected != value:
                self.__selected = value
                if self.__on_select:
                    self.__on_select(self)

        @property
        def attr_name(self) -> str:
            return self.__attr_name

        @property
        def attr_value(self) -> Any:
            return self.__cred_info.get('attrs', {}).get(self.__attr_name, None)

        @property
        def cred_id(self) -> str:
            """Credential id stored in Wallet"""
            return self.__cred_info['cred_id']

        @property
        def cred_info(self) -> dict:
            return self.__cred_info

    def __init__(self):
        # Self attested attributes as map referent_id to Attribute {referent_id: SelfAttestedAttribute}
        self.self_attested_attributes: Dict[str, SelfIdentity.SelfAttestedAttribute] = {}
        # Requested attributes as map referent_id to array of CredAttribute variants loaded from Wallet
        self.requested_attributes: Dict[str, List[SelfIdentity.CredAttribute]] = {}
        # Requested predicates as map referent_id to array of CredAttribute variants loaded from Wallet
        self.requested_predicates: Dict[str, List[SelfIdentity.CredAttribute]] = {}
        # Attributes that not found in Wallet: array of referent id
        self.non_processed = []
        #
        self.__mute = False
        self.__proof_request = None

    @property
    def proof_request(self) -> Optional[dict]:
        return self.__proof_request

    async def load(
            self, self_attested_identity: dict, proof_request: dict,
            extra_query: dict = None, limit_referents=1, default_value: Any = ''
    ) -> bool:
        self.__clear()
        self.__proof_request = proof_request
        # Stage-1: load self attested attributes
        for referent_id, data in proof_request.get('requested_attributes', {}).items():
            restrictions = data.get('restrictions', None)
            if not restrictions:
                if 'name' in data:
                    attr_name = data['name']
                    attr_value = self_attested_identity.get(attr_name, default_value)
                    self.self_attested_attributes[referent_id] = SelfIdentity.SelfAttestedAttribute(referent_id, attr_name, attr_value)
        # Stage-2: load proof-response
        proof_response = await sirius_sdk.AnonCreds.prover_search_credentials_for_proof_req(
            proof_request, extra_query=extra_query, limit_referents=limit_referents
        )
        # Stage-3: fill requested attributes
        for referent_id, cred_infos in proof_response['requested_attributes'].items():
            if len(cred_infos) > limit_referents:
                cred_infos = cred_infos[:limit_referents]  # libindy issue
            if referent_id not in self.self_attested_attributes:
                if cred_infos:
                    attr_name = proof_request['requested_attributes'].get(referent_id, {}).get('name', None)
                    attr_variants = self.requested_attributes.get(referent_id, [])
                    for i, item in enumerate(cred_infos):
                        attr_value = item.get('attrs', {}).get(attr_name, None)
                        cred_attrib = SelfIdentity.CredAttribute(
                            uid=f'{referent_id}:{i}',
                            cred_info=item['cred_info'],
                            revealed=True,
                            attr_name=attr_name,
                            on_select=self.__on_cred_attrib_select
                        )
                        if not attr_variants:
                            cred_attrib.is_selected = True
                        attr_variants.append(cred_attrib)
                    # Fill referent_id with attr alternatives variants
                    self.requested_attributes[referent_id] = attr_variants
                else:
                    self.non_processed.append(referent_id)
        # Stage-4: fill requested predicates
        for referent_id, cred_infos in proof_response['requested_predicates'].items():
            if len(cred_infos) > limit_referents:
                cred_infos = cred_infos[:limit_referents]  # libindy issue
            if cred_infos:
                attr_name = proof_request['requested_predicates'].get(referent_id, {}).get('name', None)
                attr_variants = self.requested_predicates.get(referent_id, [])
                for i, item in enumerate(cred_infos):
                    cred_attrib = SelfIdentity.CredAttribute(
                        uid=f'{referent_id}:{i}',
                        cred_info=item['cred_info'],
                        revealed=False,  # hide value for predicate requests
                        attr_name=attr_name,
                        on_select=self.__on_cred_attrib_select
                    )
                    if not attr_variants:
                        cred_attrib.is_selected = True
                    attr_variants.append(cred_attrib)
                    # Fill referent_id with attr alternatives variants
                    self.requested_predicates[referent_id] = attr_variants
                else:
                    self.non_processed.append(referent_id)
        return self.is_filled

    @property
    def is_filled(self) -> bool:
        return len(self.non_processed) == 0

    def __on_cred_attrib_select(self, emitter: CredAttribute):
        # Save from recursion calls
        if self.__mute:
            return
        # Fire
        self.__mute = True
        try:
            referent_id, index = emitter.uid.split(':')
            neighbours = self.requested_attributes.get(referent_id, []) or self.requested_predicates.get(referent_id, [])
            for neighbour in neighbours:
                if neighbour.uid != emitter.uid and neighbour.is_selected:
                    neighbour.is_selected = False
        finally:
            self.__mute = False

    def __clear(self):
        self.self_attested_attributes.clear()
        self.requested_attributes.clear()
        self.requested_predicates.clear()
        self.non_processed.clear()
        self.__proof_request = None


class ProverInteractiveMode:
    """Wrap Prover->Verifier inter-communication in single interface
    """

    def __init__(
            self, my_did: str, pool_name: str, master_secret_id: str, co: AbstractP2PCoProtocol,
            self_attested_identity: dict = None, default_value: Any = ''
    ):
        self.__self_attested_identity = self_attested_identity or {}
        self.__default_value = default_value
        self.__master_secret_id = master_secret_id
        self.__my_did = my_did
        self.__pool_name = pool_name
        self.__thread_id = None
        self.__version = '1.0'
        self.__coprotocol = co

    async def fetch(self, request: RequestPresentationMessage, extra_query: dict = None, limit_referents=1) -> SelfIdentity:
        """Fetch request correspondent data from Wallet

        :param request: Verifier request
        :param extra_query: Wallet extra-query
        :param limit_referents: max num of fetching creds
        :return: SelfIdentity
        """
        self_identity = SelfIdentity()
        await self_identity.load(
            self_attested_identity=self.__self_attested_identity,
            proof_request=request.proof_request,
            extra_query=extra_query,
            limit_referents=limit_referents,
            default_value=self.__default_value
        )
        if request.please_ack:
            self.__thread_id = request.ack_message_id
        else:
            self.__thread_id = request.id
        self.__version = request.version
        return self_identity

    async def prove(self, identity: SelfIdentity) -> (bool, Optional[PresentProofProblemReport]):
        if not identity.is_filled:
            problem_report = PresentProofProblemReport(
                REQUEST_PROCESSING_ERROR, 'No proof correspondent to proof-request'
            )
            await self.__coprotocol.send(problem_report)
            return False, problem_report
        schemas = {}
        credential_defs = {}
        rev_states = {}
        all_infos = []
        opts = CacheOptions()
        requested_credentials = {
            'self_attested_attributes': {},
            'requested_attributes': {},
            'requested_predicates': {}
        }
        # Stage-1: self attested attributes
        for referent_id, self_attest_attr in identity.self_attested_attributes.items():
            requested_credentials['self_attested_attributes'][referent_id] = self_attest_attr.value
        # Stage-2: requested attributes
        for referent_id, attr_variants in identity.requested_attributes.items():
            selected_variants = [var for var in attr_variants if var.is_selected] or [attr_variants[0]]
            selected_variant = selected_variants[0]
            info = {
                'cred_id': selected_variant.cred_info['referent'],
                'revealed': selected_variant.revealed
            }
            requested_credentials['requested_attributes'][referent_id] = info
            all_infos.append(selected_variant.cred_info)
        # Stage-3: requested predicates
        for referent_id, pred_variants in identity.requested_predicates.items():
            selected_predicates = [pred for pred in pred_variants if pred.is_selected] or [pred_variants[0]]
            selected_predicate = selected_predicates[0]
            info = {
                'cred_id': selected_predicate.cred_info['referent_id'],
            }
            if selected_predicate.revealed is True:
                info['revealed'] = True
            requested_credentials['requested_attributes'][referent_id] = info
            all_infos.append(selected_predicate.cred_info)
        # Stage-4: fill other data
        for cred_info in all_infos:
            schema_id = cred_info['schema_id']
            cred_def_id = cred_info['cred_def_id']
            schema = await sirius_sdk.Cache.get_schema(
                pool_name=self.__pool_name, submitter_did=self.__my_did,
                id_=schema_id, options=opts
            )
            cred_def = await sirius_sdk.Cache.get_cred_def(
                pool_name=self.__pool_name, submitter_did=self.__my_did,
                id_=cred_def_id, options=opts
            )
            schemas[schema_id] = schema
            credential_defs[cred_def_id] = cred_def
        # Stage-5: Build Proof
        proof = await sirius_sdk.AnonCreds.prover_create_proof(
            proof_req=identity.proof_request,
            requested_credentials=requested_credentials,
            master_secret_name=self.__master_secret_id,
            schemas=schemas,
            credential_defs=credential_defs,
            rev_states=rev_states
        )
        presentation_msg = PresentationMessage(proof, version=self.__version)
        presentation_msg.please_ack = True
        if self.__thread_id:
            presentation_msg.thread_id = self.__thread_id
        # Switch to Verifier
        ok, resp = await self.__coprotocol.switch(presentation_msg)
        if ok:
            if isinstance(resp, Ack) or isinstance(resp, PresentationAck):
                return True, None
            elif isinstance(resp, PresentProofProblemReport):
                return False, resp
            else:
                problem_report = PresentProofProblemReport(
                    RESPONSE_FOR_UNKNOWN_REQUEST, 'Unexpected response @type: %s' % str(resp.type)
                )
                await self.__coprotocol.send(problem_report)
                return False, problem_report
        else:
            problem_report = PresentProofProblemReport(
                RESPONSE_PROCESSING_ERROR, 'Response awaiting terminated by timeout'
            )
            await self.__coprotocol.send(problem_report)
            return False, problem_report
