import logging
from abc import abstractmethod
import contextlib
from typing import Union
from datetime import datetime, timedelta

import sirius_sdk
from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.hub import CoProtocolP2P
from sirius_sdk.agent.ledger import Ledger
from sirius_sdk.agent.aries_rfc.utils import utc_to_str
from sirius_sdk.agent.wallet.abstract.cache import CacheOptions
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.agent.aries_rfc.feature_0015_acks import Ack, Status
from sirius_sdk.agent.aries_rfc.feature_0037_present_proof.messages import *
from sirius_sdk.agent.aries_rfc.feature_0037_present_proof.error_codes import *
from sirius_sdk.agent.aries_rfc.feature_0037_present_proof.interactive import ProverInteractiveMode


class BaseVerifyStateMachine(AbstractStateMachine):

    def __init__(self, time_to_live: int = 60, logger=None, *args, **kwargs):
        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self._problem_report: Optional[PresentProofProblemReport] = None
        self.__time_to_live = time_to_live
        self.__coprotocol: Optional[CoProtocolP2P] = None

    @property
    def time_to_live(self) -> Optional[int]:
        return self.__time_to_live

    @property
    def problem_report(self) -> PresentProofProblemReport:
        return self._problem_report

    @contextlib.asynccontextmanager
    async def coprotocol(self, pairwise: Pairwise):
        self.__coprotocol = CoProtocolP2P(
            pairwise=pairwise,
            protocols=[BasePresentProofMessage.PROTOCOL, Ack.PROTOCOL],
            time_to_live=self.time_to_live
        )
        self._register_for_aborting(self.__coprotocol)
        try:
            try:
                yield self.__coprotocol
            except OperationAbortedManually:
                await self.log(progress=100, message='Aborted')
                raise StateMachineAborted('Aborted by User')
        finally:
            await self.__coprotocol.clean()
            self._unregister_for_aborting(self.__coprotocol)

    async def switch(self, request: BasePresentProofMessage, response_classes: list = None) -> Union[BasePresentProofMessage, Ack]:
        while True:
            ok, resp = await self.__coprotocol.switch(request)
            if ok:
                if isinstance(resp, BasePresentProofMessage) or isinstance(resp, Ack):
                    try:
                        resp.validate()
                    except SiriusValidationError as e:
                        raise StateMachineTerminatedWithError(
                            RESPONSE_PROCESSING_ERROR if self._is_leader() else REQUEST_PROCESSING_ERROR,
                            e.message
                        )
                    if response_classes:
                        if any([isinstance(resp, cls) for cls in response_classes]):
                            return resp
                        else:
                            logging.warning('Unexpected @type: %s\n%s' % (str(resp.type), json.dumps(resp, indent=2)))
                    else:
                        return resp
                elif isinstance(resp, PresentProofProblemReport):
                    raise StateMachineTerminatedWithError(resp.problem_code, resp.explain, notify=False)
                else:
                    raise StateMachineTerminatedWithError(
                        RESPONSE_PROCESSING_ERROR if self._is_leader() else REQUEST_PROCESSING_ERROR,
                        'Unexpected response @type: %s' % str(resp.type)
                    )
            else:
                raise StateMachineTerminatedWithError(
                    RESPONSE_PROCESSING_ERROR if self._is_leader() else REQUEST_PROCESSING_ERROR,
                    'Response awaiting terminated by timeout'
                )

    async def send(self, msg: Union[BasePresentProofMessage, Ack, PresentProofProblemReport]):
        await self.__coprotocol.send(msg)

    @abstractmethod
    def _is_leader(self) -> bool:
        raise NotImplemented


class Verifier(BaseVerifyStateMachine):
    """Implementation of Verifier role for present-proof protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0037-present-proof
    """

    def __init__(self, prover: Pairwise, ledger: Ledger, time_to_live: int = 60, logger=None, *args, **kwargs):
        """
        :param prover: Prover described as pairwise instance.
          (Assumed pairwise was established earlier: statically or via connection-protocol)
        :param ledger: network (DKMS) name that is used to verify credentials presented by prover
          (Assumed Ledger was configured earlier - pool-genesis file was uploaded and name was set)
        """

        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self.__prover = prover
        self.__pool_name = ledger.name
        self.__requested_proof = None
        self.__revealed_attrs = None

    @property
    def requested_proof(self) -> Optional[dict]:
        return self.__requested_proof

    @property
    def revealed_attrs(self) -> Optional[dict]:
        return self.__revealed_attrs

    async def verify(
            self, proof_request: dict, translation: List[AttribTranslation] = None,
            comment: str = None, locale: str = BasePresentProofMessage.DEF_LOCALE, proto_version: str = None
    ) -> bool:
        """
        :param proof_request: Hyperledger Indy compatible proof-request
        :param translation: human readable attributes translations
        :param comment: human readable comment from Verifier to Prover
        :param locale: locale, for example "en" or "ru"
        :param proto_version: 0037 protocol version, for example 1.0 or 1.1
        """
        async with self.coprotocol(pairwise=self.__prover):
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

                # Switch to await participant action
                presentation = await self.switch(request_msg, [PresentationMessage])
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
                        schemas[schema_id] = await sirius_sdk.Cache.get_schema(
                            self.__pool_name, self.__prover.me.did, schema_id, opts
                        )
                    if cred_def_id and cred_def_id not in credential_defs:
                        credential_defs[cred_def_id] = await sirius_sdk.Cache.get_cred_def(
                            self.__pool_name, self.__prover.me.did, cred_def_id, opts
                        )
                success = await sirius_sdk.AnonCreds.verifier_verify_proof(
                    proof_request=proof_request,
                    proof=presentation.proof,
                    schemas=schemas,
                    credential_defs=credential_defs,
                    rev_reg_defs=rev_reg_defs,
                    rev_regs=rev_regs
                )
                if success:
                    self.__requested_proof = presentation.proof['requested_proof']

                    # Parse response and fill revealed attrs
                    revealed_attrs = {}
                    for ref_id, value in self.__requested_proof['self_attested_attrs'].items():
                        if ref_id in proof_request['requested_attributes']:
                            if 'name' in proof_request['requested_attributes'][ref_id]:
                                attr_name = proof_request['requested_attributes'][ref_id]['name']
                                revealed_attrs[attr_name] = value
                    for ref_id, data in self.__requested_proof['revealed_attrs'].items():
                        if ref_id in proof_request['requested_attributes']:
                            if 'name' in proof_request['requested_attributes'][ref_id]:
                                attr_name = proof_request['requested_attributes'][ref_id]['name']
                                revealed_attrs[attr_name] = data['raw']
                    if revealed_attrs:
                        self.__revealed_attrs = revealed_attrs

                    # Send Ack
                    ack = PresentationAck(
                        thread_id=presentation.ack_message_id if presentation.please_ack else presentation.id,
                        status=Status.OK
                    )
                    await self.log(progress=100, message='Verifying terminated successfully')
                    await self.send(ack)
                    return True
                else:
                    await self.log(progress=100, message='Verifying terminated with ERROR')
                    raise StateMachineTerminatedWithError(VERIFY_ERROR, 'Verifying return false')
            except StateMachineTerminatedWithError as e:
                self._problem_report = PresentProofProblemReport(
                    e.problem_code, e.explain
                )
                await self.log(
                    progress=100, message=f'Terminated with error',
                    problem_code=e.problem_code, explain=e.explain
                )
                if e.notify:
                    await self.send(self._problem_report)
                return False

    def _is_leader(self) -> bool:
        return True


class Prover(BaseVerifyStateMachine):
    """Implementation of Prover role for present-proof protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0037-present-proof
    """

    def __init__(
            self, verifier: Pairwise, ledger: Ledger,
            time_to_live: int = 60, logger=None, self_attested_identity: dict = None, *args, **kwargs
    ):
        """
        :param verifier: Verifier described as pairwise instance.
          (Assumed pairwise was established earlier: statically or via connection-protocol)
        :param ledger: network (DKMS) name that is used to verify credentials presented by prover
          (Assumed Ledger was configured earlier - pool-genesis file was uploaded and name was set)
        :param self_attested_identity: attributes dictionary {attr_name: value} to fill self_attested_attributes for requested attribs with no restrictions
        """

        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self.__verifier = verifier
        self.__pool_name = ledger.name
        self.__self_attested_identity = self_attested_identity or {}
        self.__interactive: Optional[ProverInteractiveMode] = None

    @property
    def interactive(self) -> Optional[ProverInteractiveMode]:
        """Return Interactive mode wrapper when prove_interactive was called"""
        if self.__interactive is None:
            logging.warning('Run code in prove_interactive context to allocate property!')
        return self.__interactive

    async def prove(self, request: RequestPresentationMessage, master_secret_id: str) -> bool:
        """Prove in automate mode

        :param request: Verifier request
        :param master_secret_id: prover secret id
        """
        async with self.coprotocol(pairwise=self.__verifier):
            try:
                # Step-1: Process proof-request
                await self.log(progress=10, message='Received proof request', payload=dict(request))
                await self.log(message='proof_request', payload=dict(request.proof_request))
                try:
                    request.validate()
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, e.message)
                cred_infos, schemas, credential_defs, rev_states = await self._extract_credentials_info(
                    request.proof_request, self.__pool_name
                )

                if cred_infos.get('requested_attributes', None) or cred_infos.get('requested_predicates', None) or cred_infos.get('self_attested_attributes', None):
                    # Step-2: Build proof
                    proof = await sirius_sdk.AnonCreds.prover_create_proof(
                        proof_req=request.proof_request,
                        requested_credentials=cred_infos,
                        master_secret_name=master_secret_id,
                        schemas=schemas,
                        credential_defs=credential_defs,
                        rev_states=rev_states
                    )
                    # Step-3: Send proof and wait Ack to check success from Verifier side
                    presentation_msg = PresentationMessage(proof, version=request.version)
                    presentation_msg.please_ack = True
                    if request.please_ack:
                        presentation_msg.thread_id = request.ack_message_id
                    else:
                        presentation_msg.thread_id = request.id

                    # Step-3: Wait ACK
                    await self.log(progress=50, message='Send presentation')

                    # Switch to await participant action
                    ack = await self.switch(presentation_msg, [Ack, PresentProofProblemReport])

                    if isinstance(ack, Ack) or isinstance(ack, PresentationAck):
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
                self._problem_report = PresentProofProblemReport(
                    e.problem_code, e.explain
                )
                await self.log(
                    progress=100, message=f'Terminated with error',
                    problem_code=e.problem_code, explain=e.explain
                )
                if e.notify:
                    await self.send(self._problem_report)
                return False

    @contextlib.asynccontextmanager
    async def prove_interactive(self, master_secret_id: str):
        """Prove in interactive mode: user may select actual cred from multiple variants or propose proof_request to Verifier

        :param master_secret_id: prover secret id
        """
        async with self.coprotocol(pairwise=self.__verifier) as co:
            self.__interactive = ProverInteractiveMode(
                my_did=self.__verifier.me.did,
                pool_name=self.__pool_name,
                master_secret_id=master_secret_id,
                co=co,
                self_attested_identity=self.__self_attested_identity
            )
            try:
                yield self.__interactive
            finally:
                # clean ref
                self.__interactive = None

    async def _extract_credentials_info(self, proof_request, pool_name: str) -> (dict, dict, dict, dict):
        # Extract credentials from wallet that satisfy to request
        proof_response = await sirius_sdk.AnonCreds.prover_search_credentials_for_proof_req(
            proof_request, limit_referents=1
        )
        schemas = {}
        credential_defs = {}
        rev_states = {}
        opts = CacheOptions()
        requested_credentials = {
            'self_attested_attributes': {},
            'requested_attributes': {},
            'requested_predicates': {}
        }
        requested_attributes_with_no_restrictions = {}
        for referent_id, data in proof_request.get('requested_attributes', {}).items():
            restrictions = data.get('restrictions', [])
            if not restrictions:
                if 'names' in data:
                    requested_attributes_with_no_restrictions[referent_id] = data['names']
                if 'name' in data:
                    requested_attributes_with_no_restrictions[referent_id] = [data['name']]
        all_infos = []
        for referent_id, cred_infos in proof_response['requested_attributes'].items():
            if referent_id in requested_attributes_with_no_restrictions:
                attr_names = requested_attributes_with_no_restrictions[referent_id]
                for attr_name in attr_names:
                    if attr_name in self.__self_attested_identity:
                        requested_credentials['self_attested_attributes'][referent_id] = self.__self_attested_identity[attr_name]
                    else:
                        # set to empty str by default
                        requested_credentials['self_attested_attributes'][referent_id] = ''
            else:
                if cred_infos:
                    cred_info = cred_infos[0]['cred_info']  # Get first
                    info = {
                        'cred_id': cred_info['referent'],
                        'revealed': True
                    }
                    requested_credentials['requested_attributes'][referent_id] = info
                    all_infos.append(cred_info)
        for referent_id, predicates in proof_response['requested_predicates'].items():
            if predicates:
                pred_info = predicates[0]['cred_info']  # Get first
                info = {
                    'cred_id': pred_info['referent']
                }
                requested_credentials['requested_predicates'][referent_id] = info
                all_infos.append(pred_info)
        for cred_info in all_infos:
            schema_id = cred_info['schema_id']
            cred_def_id = cred_info['cred_def_id']
            schema = await sirius_sdk.Cache.get_schema(
                pool_name=pool_name, submitter_did=self.__verifier.me.did,
                id_=schema_id, options=opts
            )
            cred_def = await sirius_sdk.Cache.get_cred_def(
                pool_name=pool_name, submitter_did=self.__verifier.me.did,
                id_=cred_def_id, options=opts
            )
            schemas[schema_id] = schema
            credential_defs[cred_def_id] = cred_def
        return requested_credentials, schemas, credential_defs, rev_states

    def _is_leader(self) -> bool:
        return False
