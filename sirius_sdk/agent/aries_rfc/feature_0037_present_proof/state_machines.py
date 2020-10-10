from typing import List, Union
from datetime import datetime, timedelta

from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.agent.aries_rfc.utils import utc_to_str
from sirius_sdk.agent.wallet.abstract.anoncreds import AbstractAnonCreds
from sirius_sdk.agent.wallet.abstract.cache import AbstractCache, CacheOptions
from sirius_sdk.agent.sm import AbstractStateMachine, StateMachineTerminatedWithError, StateMachineAborted
from sirius_sdk.agent.aries_rfc.feature_0015_acks import Ack, Status
from sirius_sdk.agent.aries_rfc.feature_0037_present_proof.messages import *


PROPOSE_NOT_ACCEPTED = "propose_not_accepted"
RESPONSE_NOT_ACCEPTED = "response_not_accepted"
RESPONSE_PROCESSING_ERROR = "response_processing_error"
REQUEST_NOT_ACCEPTED = "request_not_accepted"
RESPONSE_FOR_UNKNOWN_REQUEST = "response_for_unknown_request"
REQUEST_PROCESSING_ERROR = 'request_processing_error'
VERIFY_ERROR = 'verify_error'


class Verifier(AbstractStateMachine):
    """Implementation of Verifier role for present-proof protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0037-present-proof
    """

    def __init__(
            self, prover: Pairwise, pool_name: str,
            api: AbstractAnonCreds = None, cache: AbstractCache = None, *args, **kwargs
    ):
        """
        :param prover: Prover described as pairwise instance.
          (Assumed pairwise was established earlier: statically or via connection-protocol)
        :param pool_name: network (DKMS) name that is used to verify credentials presented by prover
        :param api: optionally passed anon-creds api that implemented outside wallet
          (by default state-machine will use Indy SDK on Agent side)
        :param cache: optionally passed caching api that implemented outside wallet
          (by default state-machine will use Indy SDK on Agent side)
        """

        super().__init__(*args, **kwargs)
        self.__api = api
        self.__api_internal = api is None
        self.__prover = prover
        self.__thread_id = None
        self.__transport = None
        self.__cache = cache
        self.__cache_internal = cache is None
        self.__problem_report = None
        self.__pool_name = pool_name

    async def verify(
            self, proof_request: dict, translation: List[AttribTranslation] = None,
            comment: str = None, locale: str = BasePresentProofMessage.DEF_LOCALE, proto_version: str = None
    ):
        await self.__start()
        try:
            try:
                # Step-1: Send proof request
                expires_time = datetime.utcnow() + timedelta(seconds=self.time_to_live)
                request_msg = RequestPresentationMessage(
                    proof_request=proof_request,
                    translation=translation,
                    comment=comment,
                    locale=locale,
                    expires_time=utc_to_str(expires_time),
                    version=proto_version
                )
                request_msg.please_ack = True
                await self.log(progress=30, message='Send request', payload=dict(request_msg))

                presentation = await self.__switch(request_msg)
                if not isinstance(presentation, PresentationMessage):
                    raise StateMachineTerminatedWithError(
                        RESPONSE_NOT_ACCEPTED, 'Unexpected @type: %s' % str(presentation.type)
                    )
                await self.log(progress=60, message='Presentation received')

                # Step-2 Verify
                identifiers = presentation.proof.get('identifiers', [])
                schemas = {}
                credential_defs = {}
                rev_reg_defs = {}
                rev_regs = {}
                opts = CacheOptions()
                for identifier in identifiers:
                    schema_id = identifier['schema_id']
                    cred_def_id = identifier['cred_def_id']
                    rev_reg_id = identifier['rev_reg_id']
                    if schema_id and schema_id not in schemas:
                        schemas[schema_id] = await self.__cache.get_schema(
                            self.__pool_name, self.__prover.me.did, schema_id, opts
                        )
                    if cred_def_id and cred_def_id not in credential_defs:
                        credential_defs[cred_def_id] = await self.__cache.get_cred_def(
                            self.__pool_name, self.__prover.me.did, cred_def_id, opts
                        )
                success = await self.__api.verifier_verify_proof(
                    proof_request=proof_request,
                    proof=presentation.proof,
                    schemas=schemas,
                    credential_defs=credential_defs,
                    rev_reg_defs=rev_reg_defs,
                    rev_regs=rev_regs
                )
                if success:
                    ack = Ack(
                        thread_id=presentation.ack_message_id if presentation.please_ack else presentation.id,
                        status=Status.OK
                    )
                    await self.log(progress=100, message='Verifying terminated successfully')
                    await self.__send(ack)
                    return True
                else:
                    await self.log(progress=100, message='Verifying terminated with ERROR')
                    raise StateMachineTerminatedWithError(VERIFY_ERROR, 'Verifying return false')
            except StateMachineTerminatedWithError as e:
                self.__problem_report = PresentProofProblemReport(
                    e.problem_code, e.explain, thread_id=self.__thread_id
                )
                await self.log(
                    progress=100, message=f'Terminated with error',
                    problem_code=e.problem_code, explain=e.explain
                )
                if e.notify:
                    await self.__send(self.__problem_report)
                return False
        finally:
            await self.__stop()

    @property
    def problem_report(self) -> PresentProofProblemReport:
        return self.__problem_report

    @property
    def protocols(self) -> List[str]:
        return [BasePresentProofMessage.PROTOCOL, Ack.PROTOCOL]

    async def abort(self):
        await super().abort()
        if self.__transport and self.__transport.is_started:
            self.__problem_report = PresentProofProblemReport(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Operation is aborted by owner',
                thread_id=self.__thread_id
            )
            await self.__transport.send(self.__problem_report)

    async def __start(self):
        self.__transport = await self.transports.spawn(self.__prover)
        await self.__transport.start(self.protocols, self.time_to_live)
        if self.__api_internal:
            self.__api = self.__transport.wallet.anoncreds
        if self.__cache_internal:
            self.__cache = self.__transport.wallet.cache

    async def __stop(self):
        if self.__transport:
            await self.__transport.stop()
            self.__transport = None
            if self.__api_internal:
                self.__api = None
            if self.__cache_internal:
                self.__cache = None

    async def __switch(self, request: BasePresentProofMessage) -> Union[BasePresentProofMessage, Ack]:
        ok, resp = await self.__transport.switch(request)
        if self.is_aborted:
            await self.log(progress=100, message='Aborted')
            raise StateMachineAborted
        if ok:
            self.__thread_id = None
            if isinstance(resp, BasePresentProofMessage):
                if resp.please_ack:
                    self.__thread_id = resp.ack_message_id
            if isinstance(resp, BasePresentProofMessage) or isinstance(resp, Ack):
                try:
                    resp.validate()
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(RESPONSE_PROCESSING_ERROR, e.message)
                return resp
            elif isinstance(resp, PresentProofProblemReport):
                raise StateMachineTerminatedWithError(resp.problem_code, resp.explain, notify=False)
            else:
                raise StateMachineTerminatedWithError(RESPONSE_PROCESSING_ERROR, 'Unexpected response @type: %s' % str(resp.type))
        else:
            raise StateMachineTerminatedWithError(RESPONSE_PROCESSING_ERROR, 'Response awaiting terminated by timeout')

    async def __send(self, msg: Union[BasePresentProofMessage, Ack, PresentProofProblemReport]):
        await self.__transport.send(msg)


class Prover(AbstractStateMachine):
    """Implementation of Prover role for present-proof protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0037-present-proof
    """

    def __init__(
            self, verifier: Pairwise, pool_name: str,
            api: AbstractAnonCreds = None, cache: AbstractCache = None,
            *args, **kwargs
    ):
        """
        :param verifier: Verifier described as pairwise instance.
          (Assumed pairwise was established earlier: statically or via connection-protocol)
        :param pool_name: network (DKMS) name that is used to verify credentials presented by prover
        :param api: optionally passed anon-creds api that implemented outside wallet
          (by default state-machine will use Indy SDK on Agent side)
        :param cache: optionally passed caching api that implemented outside wallet
          (by default state-machine will use Indy SDK on Agent side)
        """

        super().__init__(*args, **kwargs)
        self.__api = api
        self.__api_internal = api is None
        self.__verifier = verifier
        self.__thread_id = None
        self.__transport = None
        self.__cache = cache
        self.__cache_internal = cache is None
        self.__problem_report = None
        self.__pool_name = pool_name

    async def prove(self, request: RequestPresentationMessage, master_secret_id: str) -> bool:
        await self.__start()
        try:
            try:
                # Step-1: Process proof-request
                await self.log(progress=10, message='Received proof request', payload=dict(request))
                try:
                    request.validate()
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, e.message)
                cred_infos, schemas, credential_defs, rev_states = await self._extract_credentials_info(
                    request.proof_request, self.__pool_name
                )
                if cred_infos.get('requested_attributes', None) or cred_infos.get('requested_predicates', None):
                    # Step-2: Build proof
                    proof = await self.__api.prover_create_proof(
                        proof_req=request.proof_request,
                        requested_credentials=cred_infos,
                        master_secret_name=master_secret_id,
                        schemas=schemas,
                        credential_defs=credential_defs,
                        rev_states=rev_states
                    )
                    # Step-3: Send proof and wait Ack to check success from Verifier side
                    presentation_msg = PresentationMessage(proof)
                    presentation_msg.please_ack = True
                    if request.please_ack:
                        presentation_msg.thread_id = request.ack_message_id

                    # Step-3: Wait ACK
                    await self.log(progress=50, message='Send presentation')
                    ack = await self.__switch(presentation_msg)
                    if isinstance(ack, Ack):
                        await self.log(progress=100, message='Verify OK!')
                        return True
                    elif isinstance(ack, PresentProofProblemReport):
                        await self.log(progress=100, message='Verify ERROR!')
                        return False
                    else:
                        raise StateMachineTerminatedWithError(
                            RESPONSE_FOR_UNKNOWN_REQUEST, 'Unexpected response @type: %s' % str(ack.type)
                        )
                else:
                    raise StateMachineTerminatedWithError(
                        REQUEST_PROCESSING_ERROR, 'No proof correspondent to proof-request'
                    )
            except StateMachineTerminatedWithError as e:
                self.__problem_report = PresentProofProblemReport(
                    e.problem_code, e.explain, thread_id=self.__thread_id
                )
                await self.log(
                    progress=100, message=f'Terminated with error',
                    problem_code=e.problem_code, explain=e.explain
                )
                if e.notify:
                    await self.__send(self.__problem_report)
                return False
        finally:
            await self.__stop()

    @property
    def problem_report(self) -> PresentProofProblemReport:
        return self.__problem_report

    @property
    def protocols(self) -> List[str]:
        return [BasePresentProofMessage.PROTOCOL, Ack.PROTOCOL]

    async def abort(self):
        await super().abort()
        if self.__transport and self.__transport.is_started:
            self.__problem_report = PresentProofProblemReport(
                problem_code=RESPONSE_PROCESSING_ERROR,
                explain='Operation is aborted by owner',
                thread_id=self.__thread_id
            )
            await self.__transport.send(self.__problem_report)

    async def _extract_credentials_info(self, proof_request, pool_name: str) -> (dict, dict, dict, dict):
        # Extract credentials from wallet that satisfy to request
        proof_response = await self.__api.prover_search_credentials_for_proof_req(proof_request, limit_referents=1)
        schemas = {}
        credential_defs = {}
        rev_states = {}
        opts = CacheOptions()
        requested_credentials = {
            'self_attested_attributes': {},
            'requested_attributes': {},
            'requested_predicates': {}
        }
        all_infos = []
        for referent_id, cred_infos in proof_response['requested_attributes'].items():
            cred_info = cred_infos[0]['cred_info']  # Get first
            info = {
                'cred_id': cred_info['referent'],
                'revealed': True
            }
            requested_credentials['requested_attributes'][referent_id] = info
            all_infos.append(cred_info)
        for referent_id, predicates in proof_response['requested_predicates'].items():
            pred_info = predicates[0]['cred_info']  # Get first
            info = {
                'cred_id': pred_info['referent']
            }
            requested_credentials['requested_predicates'][referent_id] = info
            all_infos.append(pred_info)
        for cred_info in all_infos:
            schema_id = cred_info['schema_id']
            cred_def_id = cred_info['cred_def_id']
            schema = await self.__cache.get_schema(
                pool_name=pool_name, submitter_did=self.__verifier.me.did,
                id_=schema_id, options=opts
            )
            cred_def = await self.__cache.get_cred_def(
                pool_name=pool_name, submitter_did=self.__verifier.me.did,
                id_=cred_def_id, options=opts
            )
            schemas[schema_id] = schema
            credential_defs[cred_def_id] = cred_def
        return requested_credentials, schemas, credential_defs, rev_states

    async def __start(self):
        self.__transport = await self.transports.spawn(self.__verifier)
        await self.__transport.start(self.protocols, self.time_to_live)
        if self.__api_internal:
            self.__api = self.__transport.wallet.anoncreds
        if self.__cache_internal:
            self.__cache = self.__transport.wallet.cache

    async def __stop(self):
        if self.__transport:
            await self.__transport.stop()
            self.__transport = None
            if self.__api_internal:
                self.__api = None
            if self.__cache_internal:
                self.__cache = None

    async def __switch(self, request: BasePresentProofMessage) -> Union[BasePresentProofMessage, Ack]:
        ok, resp = await self.__transport.switch(request)
        if self.is_aborted:
            await self.log(progress=100, message='Aborted')
            raise StateMachineAborted
        if ok:
            self.__thread_id = None
            if isinstance(resp, BasePresentProofMessage):
                if resp.please_ack:
                    self.__thread_id = resp.ack_message_id
            if isinstance(resp, BasePresentProofMessage) or isinstance(resp, Ack):
                try:
                    resp.validate()
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(REQUEST_PROCESSING_ERROR, e.message)
                return resp
            elif isinstance(resp, PresentProofProblemReport):
                raise StateMachineTerminatedWithError(resp.problem_code, resp.explain, notify=False)
            else:
                raise StateMachineTerminatedWithError(
                    REQUEST_PROCESSING_ERROR, 'Unexpected response @type: %s' % str(resp.type)
                )
        else:
            raise StateMachineTerminatedWithError(REQUEST_PROCESSING_ERROR, 'Response awaiting terminated by timeout')

    async def __send(self, msg: Union[BasePresentProofMessage, Ack, PresentProofProblemReport]):
        await self.__transport.send(msg)
