from typing import List, Union
from datetime import datetime, timedelta

from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.agent.codec import encode
from sirius_sdk.agent.aries_rfc.utils import utc_to_str
from sirius_sdk.agent.ledger import Schema, CredentialDefinition
from sirius_sdk.errors.indy_exceptions import WalletItemNotFound
from sirius_sdk.agent.wallet.abstract.anoncreds import AbstractAnonCreds
from sirius_sdk.agent.sm import AbstractStateMachine, StateMachineTerminatedWithError, StateMachineAborted
from sirius_sdk.agent.aries_rfc.feature_0015_acks import Ack, Status
from sirius_sdk.agent.aries_rfc.feature_0036_issue_credential.messages import *


PROPOSE_NOT_ACCEPTED = "propose_not_accepted"
OFFER_PROCESSING_ERROR = 'offer_processing_error'
REQUEST_NOT_ACCEPTED = "request_not_accepted"
ISSUE_PROCESSING_ERROR = 'issue_processing_error'
RESPONSE_FOR_UNKNOWN_REQUEST = "response_for_unknown_request"


class Issuer(AbstractStateMachine):
    """Implementation of Issuer role for Credential-issuing protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0036-issue-credential
    """
    
    def __init__(self, holder: Pairwise, api: AbstractAnonCreds = None, *args, **kwargs):
        """
        :param holder: Holder side described as pairwise instance.
          (Assumed pairwise was established earlier: statically or via connection-protocol)
        :param api: optionally passed anon-creds api that implemented outside wallet
          (by default state-machine will use Indy SDK on Agent side)
        """

        super().__init__(*args, **kwargs)
        self.__api = api
        self.__api_internal = api is None
        self.__holder = holder
        self.__thread_id = None
        self.__transport = None
        self.__problem_report = None

    async def issue(
            self, values: dict, schema: Schema, cred_def: CredentialDefinition,
            comment: str = None, locale: str = BaseIssueCredentialMessage.DEF_LOCALE,
            preview: List[Any] = None, translation: List[AttribTranslation] = None, cred_id: str = None
    ) -> bool:
        await self.__start()
        try:
            try:
                # Step-1: Send offer to holder
                offer = await self.__api.issuer_create_credential_offer(cred_def_id=cred_def.id)
                expires_time = datetime.utcnow() + timedelta(seconds=self.time_to_live)
                offer_msg = OfferCredentialMessage(
                    comment=comment,
                    locale=locale,
                    offer=offer,
                    cred_def=cred_def.body,
                    preview=preview,
                    issuer_schema=schema.body,
                    translation=translation,
                    expires_time=utc_to_str(expires_time)
                )
                offer_msg.please_ack = True
                await self.log(progress=20, message='Send offer', payload=dict(offer_msg))

                resp = await self.__switch(offer_msg)
                if not isinstance(resp, RequestCredentialMessage):
                    raise StateMachineTerminatedWithError(OFFER_PROCESSING_ERROR, 'Unexpected @type: %s' % str(resp.type))
                # Step-2: Create credential
                request_msg = resp
                await self.log(progress=40, message='Received credential request', payload=dict(request_msg))

                encoded_cred_values = dict()
                for key, value in values.items():
                    encoded_cred_values[key] = dict(raw=str(value), encoded=encode(value))
                await self.log(progress=70, message='Build credential with values', payload=encoded_cred_values)

                ret = await self.__api.issuer_create_credential(
                    cred_offer=offer,
                    cred_req=request_msg.cred_request,
                    cred_values=encoded_cred_values,
                    rev_reg_id=None,
                    blob_storage_reader_handle=None
                )
                cred, cred_revoc_id, revoc_reg_delta = ret
                # Step-3: Issue and wait Ack
                issue_msg = IssueCredentialMessage(
                    comment=comment,
                    locale=locale,
                    cred=cred,
                    cred_id=cred_id
                )
                if resp.please_ack:
                    issue_msg.thread_id = resp.ack_message_id
                issue_msg.please_ack = True
                await self.log(progress=90, message='Send Issue message', payload=dict(issue_msg))

                ack = await self.__switch(issue_msg)
                if not isinstance(ack, Ack):
                    raise StateMachineTerminatedWithError(ISSUE_PROCESSING_ERROR, 'Unexpected @type: %s' % str(resp.type))
                await self.log(progress=100, message='Issuing was terminated successfully')

            except StateMachineTerminatedWithError as e:
                self.__problem_report = IssueProblemReport(
                    e.problem_code, e.explain, thread_id=self.__thread_id
                )
                await self.log(
                    progress=100, message=f'Terminated with error',
                    problem_code=e.problem_code, explain=e.explain
                )
                if e.notify:
                    await self.__send(self.__problem_report)
                return False
            else:
                return True
        finally:
            await self.__stop()

    @property
    def problem_report(self) -> IssueProblemReport:
        return self.__problem_report

    async def abort(self):
        await super().abort()
        if self.__transport and self.__transport.is_started:
            self.__problem_report = IssueProblemReport(
                problem_code=ISSUE_PROCESSING_ERROR,
                explain='Operation is aborted by owner',
                thread_id=self.__thread_id
            )
            await self.__transport.send(self.__problem_report)

    @property
    def protocols(self) -> List[str]:
        return [BaseIssueCredentialMessage.PROTOCOL, Ack.PROTOCOL]

    async def __start(self):
        self.__transport = await self.transports.spawn(self.__holder)
        await self.__transport.start(self.protocols, self.time_to_live)
        if self.__api_internal:
            self.__api = self.__transport.wallet.anoncreds

    async def __stop(self):
        if self.__transport:
            await self.__transport.stop()
            self.__transport = None
            if self.__api_internal:
                self.__api = None

    async def __switch(self, request: BaseIssueCredentialMessage) -> Union[BaseIssueCredentialMessage, Ack]:
        ok, resp = await self.__transport.switch(request)
        if self.is_aborted:
            await self.log(progress=100, message='Aborted')
            raise StateMachineAborted
        if ok:
            self.__thread_id = None
            if isinstance(resp, BaseIssueCredentialMessage):
                if resp.please_ack:
                    self.__thread_id = resp.ack_message_id
            if isinstance(resp, BaseIssueCredentialMessage) or isinstance(resp, Ack):
                try:
                    resp.validate()
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(ISSUE_PROCESSING_ERROR, e.message)
                return resp
            elif isinstance(resp, IssueProblemReport):
                raise StateMachineTerminatedWithError(resp.problem_code, resp.explain, notify=False)
            else:
                raise StateMachineTerminatedWithError(ISSUE_PROCESSING_ERROR, 'Unexpected response @type: %s' % str(resp.type))
        else:
            raise StateMachineTerminatedWithError(ISSUE_PROCESSING_ERROR, 'Response awaiting terminated by timeout')

    async def __send(self, msg: Union[BaseIssueCredentialMessage, Ack, IssueProblemReport]):
        await self.__transport.send(msg)


class Holder(AbstractStateMachine):
    """Implementation of Holder role for Credential-issuing protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0036-issue-credential
    """

    def __init__(
            self, issuer: Pairwise,
            comment: str = None, locale: str = BaseIssueCredentialMessage.DEF_LOCALE,
            api: AbstractAnonCreds = None, *args, **kwargs
    ):
        """
        :param issuer: Issuer described as pairwise instance.
          (Assumed pairwise was established earlier: statically or via connection-protocol)
        :param comment: optional comment that describe human readable text filled by Holder for Issuer
        :param locale: optional language code. Does matter if comment is set
        :param api: optionally passed anon-creds api that implemented outside wallet
          (by default state-machine will use Indy SDK on Agent side)
        """
        super().__init__(*args, **kwargs)
        self.__api = api
        self.__api_internal = api is None
        self.__issuer = issuer
        self.__thread_id = None
        self.__problem_report = None
        self.__comment = comment
        self.__locale = locale

    async def accept(self, offer: OfferCredentialMessage, master_secret_id: str) -> (bool, Optional[str]):
        doc_uri = offer.doc_uri
        await self.__start()
        try:
            try:
                offer_msg = offer
                try:
                    offer_msg.validate()
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, e.message)
                # Step-1: Process Issuer Offer
                cred_request, cred_metadata = await self.__api.prover_create_credential_req(
                    prover_did=self.__issuer.me.did,
                    cred_offer=offer_msg.offer,
                    cred_def=offer_msg.cred_def,
                    master_secret_id=master_secret_id
                )
                # Step-2: Send request to Issuer
                request_msg = RequestCredentialMessage(
                    comment=self.__comment,
                    locale=self.__locale,
                    cred_request=cred_request,
                    doc_uri=doc_uri
                )
                if offer_msg.please_ack:
                    request_msg.thread_id = offer_msg.id
                resp = await self.__switch(request_msg)
                if not isinstance(resp, IssueCredentialMessage):
                    raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, 'Unexpected @type: %s' % str(resp.type))
                issue_msg = resp
                try:
                    issue_msg.validate()
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, e.message)
                # Step-3: Store credential
                cred_id = await self._store_credential(
                    cred_metadata, issue_msg.cred, offer.cred_def, None, issue_msg.cred_id
                )
                ack = Ack(
                    thread_id=issue_msg.ack_message_id if issue_msg.please_ack else issue_msg.id,
                    status=Status.OK,
                    doc_uri=doc_uri
                )
                await self.__send(ack)
            except StateMachineTerminatedWithError as e:
                self.__problem_report = IssueProblemReport(
                    problem_code=e.problem_code,
                    explain=e.explain,
                    doc_uri=doc_uri,
                    thread_id=self.__thread_id
                )
                await self.log(
                    progress=100, message=f'Terminated with error',
                    problem_code=e.problem_code, explain=e.explain
                )
                if e.notify:
                    await self.__send(self.__problem_report)
                return False, None
            else:
                return True, cred_id
        finally:
            await self.__stop()

    @property
    def problem_report(self) -> IssueProblemReport:
        return self.__problem_report

    @property
    def protocols(self) -> List[str]:
        return [BaseIssueCredentialMessage.PROTOCOL, Ack.PROTOCOL]

    async def abort(self):
        await super().abort()
        if self.__transport and self.__transport.is_started:
            self.__problem_report = IssueProblemReport(
                problem_code=OFFER_PROCESSING_ERROR,
                explain='Operation is aborted by owner',
                thread_id=self.__thread_id
            )
            await self.__transport.send(self.__problem_report)

    async def _store_credential(
            self, cred_metadata: dict, cred: dict, cred_def: dict, rev_reg_def: Optional[dict], cred_id: Optional[str]
    ) -> str:
        try:
            cred_older = await self.__api.prover_get_credential(cred_id)
        except WalletItemNotFound:
            cred_older = None
        if cred_older:
            # Delete older credential
            await self.__api.prover_delete_credential(cred_id)
        cred_id = await self.__api.prover_store_credential(
            cred_req_metadata=cred_metadata,
            cred=cred,
            cred_def=cred_def,
            rev_reg_def=rev_reg_def,
            cred_id=cred_id
        )
        return cred_id

    async def __start(self):
        self.__transport = await self.transports.spawn(self.__issuer)
        await self.__transport.start(self.protocols, self.time_to_live)
        if self.__api_internal:
            self.__api = self.__transport.wallet.anoncreds

    async def __stop(self):
        if self.__transport:
            await self.__transport.stop()
            self.__transport = None
            if self.__api_internal:
                self.__api = None

    async def __switch(self, request: BaseIssueCredentialMessage) -> Union[BaseIssueCredentialMessage, Ack]:
        ok, resp = await self.__transport.switch(request)
        if self.is_aborted:
            await self.log(progress=100, message='Aborted')
            raise StateMachineAborted
        if ok:
            self.__thread_id = None
            if isinstance(resp, BaseIssueCredentialMessage):
                if resp.please_ack:
                    self.__thread_id = resp.ack_message_id
            if isinstance(resp, BaseIssueCredentialMessage) or isinstance(resp, Ack):
                try:
                    resp.validate()
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, e.message)
                return resp
            elif isinstance(resp, IssueProblemReport):
                raise StateMachineTerminatedWithError(resp.problem_code, resp.explain, notify=False)
            else:
                raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, 'Unexpected issuer request @type: %s' % str(resp.type))
        else:
            raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, 'Issuer request awaiting terminated by timeout')

    async def __send(self, msg: Union[BaseIssueCredentialMessage, Ack, IssueProblemReport]):
        await self.__transport.send(msg)
