import json
import logging
import contextlib
from abc import abstractmethod
from typing import Union
from datetime import datetime, timedelta

import sirius_sdk
from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.hub import CoProtocolP2P
from sirius_sdk.agent.codec import encode
from sirius_sdk.agent.ledger import Ledger
from sirius_sdk.agent.aries_rfc.utils import utc_to_str
from sirius_sdk.agent.ledger import Schema, CredentialDefinition
from sirius_sdk.errors.indy_exceptions import WalletItemNotFound
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.agent.aries_rfc.feature_0015_acks import Ack, Status
from sirius_sdk.agent.aries_rfc.feature_0036_issue_credential.messages import *
from sirius_sdk.agent.wallet.abstract.non_secrets import RetrieveRecordOptions


PROPOSE_NOT_ACCEPTED = "propose_not_accepted"
OFFER_PROCESSING_ERROR = 'offer_processing_error'
REQUEST_NOT_ACCEPTED = "request_not_accepted"
ISSUE_PROCESSING_ERROR = 'issue_processing_error'
RESPONSE_FOR_UNKNOWN_REQUEST = "response_for_unknown_request"


class BaseIssuingStateMachine(AbstractStateMachine):

    def __init__(self, time_to_live: int = 60, logger=None, *args, **kwargs):
        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self._problem_report = None
        self.__time_to_live = time_to_live
        self.__coprotocol: Optional[CoProtocolP2P] = None

    @property
    def time_to_live(self) -> Optional[int]:
        return self.__time_to_live

    @property
    def problem_report(self) -> IssueProblemReport:
        return self._problem_report

    @contextlib.asynccontextmanager
    async def coprotocol(self, pairwise: Pairwise):
        self.__coprotocol = CoProtocolP2P(
            pairwise=pairwise,
            protocols=[BaseIssueCredentialMessage.PROTOCOL, Ack.PROTOCOL],
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

    async def switch(self, request: BaseIssueCredentialMessage, response_classes: list = None) -> Union[BaseIssueCredentialMessage, Ack]:
        while True:
            ok, resp = await self.__coprotocol.switch(request)
            if ok:
                if isinstance(resp, BaseIssueCredentialMessage) or isinstance(resp, Ack):
                    try:
                        resp.validate()
                    except SiriusValidationError as e:
                        raise StateMachineTerminatedWithError(
                            ISSUE_PROCESSING_ERROR if self._is_leader() else REQUEST_NOT_ACCEPTED,
                            e.message
                        )
                    if response_classes:
                        if any([isinstance(resp, cls) for cls in response_classes]):
                            return resp
                        else:
                            logging.warning('Unexpected @type: %s\n%s' % (str(resp.type), json.dumps(resp, indent=2)))
                    else:
                        return resp
                elif isinstance(resp, IssueProblemReport):
                    raise StateMachineTerminatedWithError(resp.problem_code, resp.explain, notify=False)
                else:
                    raise StateMachineTerminatedWithError(
                        ISSUE_PROCESSING_ERROR if self._is_leader() else REQUEST_NOT_ACCEPTED,
                        'Unexpected response @type: %s' % str(resp.type)
                    )
            else:
                raise StateMachineTerminatedWithError(
                    ISSUE_PROCESSING_ERROR if self._is_leader() else REQUEST_NOT_ACCEPTED,
                    'Response awaiting terminated by timeout'
                )

    async def send(self, msg: Union[BaseIssueCredentialMessage, Ack, IssueProblemReport]):
        await self.__coprotocol.send(msg)

    @abstractmethod
    def _is_leader(self) -> bool:
        raise NotImplemented


class Issuer(BaseIssuingStateMachine):
    """Implementation of Issuer role for Credential-issuing protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0036-issue-credential
    """

    def __init__(self, holder: Pairwise, time_to_live: int = 60, logger=None, *args, **kwargs):
        """
        :param holder: Holder side described as pairwise instance.
          (Assumed pairwise was established earlier: statically or via connection-protocol)
        """

        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self.__holder = holder

    async def issue(
            self, values: dict, schema: Schema, cred_def: CredentialDefinition,
            comment: str = None, locale: str = BaseIssueCredentialMessage.DEF_LOCALE,
            preview: List[ProposedAttrib] = None, translation: List[AttribTranslation] = None, cred_id: str = None
    ) -> bool:
        """
        :param values: credential values {"attr_name": "attr_value"}
        :param schema: credential schema
        :param cred_def: credential definition prepared and stored in Ledger earlier
        :param comment: human readable credential comment
        :param preview: credential preview
        :param locale: locale, for example "en" or "ru"
        :param translation: translation of the credential preview according to locale
        :param cred_id: credential id. Issuer may issue multiple credentials with same cred-id to give holder ability
                        to restore old credential
        """
        async with self.coprotocol(pairwise=self.__holder):
            try:
                # Step-1: Send offer to holder
                offer = await sirius_sdk.AnonCreds.issuer_create_credential_offer(cred_def_id=cred_def.id)
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
                await self.log(progress=20, message='Send offer', payload=dict(offer_msg))

                # Switch to await participant action
                resp = await self.switch(offer_msg, [RequestCredentialMessage])
                if not isinstance(resp, RequestCredentialMessage):
                    raise StateMachineTerminatedWithError(
                        OFFER_PROCESSING_ERROR, 'Unexpected @type: %s' % str(resp.type)
                    )

                # Step-2: Create credential
                request_msg = resp
                await self.log(progress=40, message='Received credential request', payload=dict(request_msg))
                encoded_cred_values = dict()
                for key, value in values.items():
                    encoded_cred_values[key] = dict(raw=str(value), encoded=encode(value))
                await self.log(progress=70, message='Build credential with values', payload=encoded_cred_values)

                ret = await sirius_sdk.AnonCreds.issuer_create_credential(
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
                await self.log(progress=90, message='Send Issue message', payload=dict(issue_msg))

                ack = await self.switch(issue_msg, [Ack])
                if isinstance(ack, Ack) or isinstance(ack, CredentialAck):
                    await self.log(progress=100, message='Issuing was terminated successfully')
                    return True
                else:
                    raise StateMachineTerminatedWithError(
                        ISSUE_PROCESSING_ERROR, 'Unexpected @type: %s' % str(resp.type)
                    )
            except StateMachineTerminatedWithError as e:
                self._problem_report = IssueProblemReport(
                    problem_code=e.problem_code,
                    explain=e.explain,
                )
                if e.notify:
                    await self.send(self._problem_report)
                await self.log(
                    progress=100, message=f'Terminated with error',
                    problem_code=e.problem_code, explain=e.explain
                )
                return False

    def _is_leader(self) -> bool:
        return True


class Holder(BaseIssuingStateMachine):
    """Implementation of Holder role for Credential-issuing protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0036-issue-credential
    """

    def __init__(
            self, issuer: Pairwise, time_to_live: int = 60, logger=None, *args, **kwargs
    ):
        """
        :param issuer: Issuer described as pairwise instance.
          (Assumed pairwise was established earlier: statically or via connection-protocol)
        """
        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self.__issuer = issuer

    async def accept(
            self, offer: OfferCredentialMessage, master_secret_id: str,
            comment: str = None, locale: str = BaseIssueCredentialMessage.DEF_LOCALE, ledger: Ledger = None
    ) -> (bool, Optional[str]):
        """
        :param offer: credential offer
        :param master_secret_id: prover master secret ID
        :param comment: human readable comment
        :param locale: locale, for example "en" or "ru"
        :param ledger: DKMS to retrieve actual schema and cred_def bodies if this not contains in Offer
        """
        doc_uri = offer.doc_uri
        async with self.coprotocol(pairwise=self.__issuer):
            try:
                offer_msg = offer
                try:
                    offer_msg.validate()
                except SiriusValidationError as e:
                    logging.warning(e.message)
                    # raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, e.message)

                # Step-1: Process Issuer Offer
                _, offer_body, cred_def_body = offer_msg.parse(mute_errors=True)
                if not offer_body:
                    raise StateMachineTerminatedWithError(
                        OFFER_PROCESSING_ERROR, 'Error while parsing cred_offer', notify=True
                    )
                if not cred_def_body:
                    if ledger:
                        cred_def = await ledger.load_cred_def(
                            offer_body['cred_def_id'], submitter_did=self.__issuer.me.did
                        )
                        cred_def_body = cred_def.body
                if not cred_def_body:
                    raise StateMachineTerminatedWithError(
                        OFFER_PROCESSING_ERROR, 'Error while parsing cred_def', notify=True
                    )
                cred_request, cred_metadata = await sirius_sdk.AnonCreds.prover_create_credential_req(
                    prover_did=self.__issuer.me.did,
                    cred_offer=offer_body,
                    cred_def=cred_def_body,
                    master_secret_id=master_secret_id
                )

                # Step-2: Send request to Issuer
                request_msg = RequestCredentialMessage(
                    comment=comment,
                    locale=locale,
                    cred_request=cred_request,
                    doc_uri=doc_uri,
                    version=offer.version
                )

                if offer.please_ack:
                    request_msg.thread_id = offer.ack_message_id
                else:
                    request_msg.thread_id = offer.id
                # Switch to await participant action
                resp = await self.switch(request_msg, [IssueCredentialMessage])
                if not isinstance(resp, IssueCredentialMessage):
                    raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, 'Unexpected @type: %s' % str(resp.type))

                issue_msg = resp
                try:
                    issue_msg.validate()
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, e.message)

                # Step-3: Store credential
                cred_id = await self._store_credential(
                    cred_metadata, issue_msg.cred, cred_def_body, None, issue_msg.cred_id
                )
                await self._store_mime_types(cred_id, offer.preview)
                ack = CredentialAck(
                    thread_id=issue_msg.ack_message_id if issue_msg.please_ack else issue_msg.id,
                    status=Status.OK,
                    doc_uri=doc_uri,
                    version=offer.version
                )
                await self.send(ack)

            except StateMachineTerminatedWithError as e:
                self._problem_report = IssueProblemReport(
                    problem_code=e.problem_code,
                    explain=e.explain,
                    doc_uri=doc_uri
                )
                await self.log(
                    progress=100, message=f'Terminated with error',
                    problem_code=e.problem_code, explain=e.explain
                )
                if e.notify:
                    await self.send(self._problem_report)
                return False, None
            else:
                return True, cred_id

    def _is_leader(self) -> bool:
        return False

    @staticmethod
    async def _store_credential(
            cred_metadata: dict, cred: dict, cred_def: dict, rev_reg_def: Optional[dict], cred_id: Optional[str]
    ) -> str:
        try:
            cred_older = await sirius_sdk.AnonCreds.prover_get_credential(cred_id)
        except WalletItemNotFound:
            cred_older = None
        if cred_older:
            # Delete older credential
            await sirius_sdk.AnonCreds.prover_delete_credential(cred_id)
        cred_id = await sirius_sdk.AnonCreds.prover_store_credential(
            cred_req_metadata=cred_metadata,
            cred=cred,
            cred_def=cred_def,
            rev_reg_def=rev_reg_def,
            cred_id=cred_id
        )
        return cred_id

    @staticmethod
    async def _store_mime_types(cred_id: str, preview: List[ProposedAttrib]):
        if preview is not None:
            mime_types = {prop_attrib["name"]: prop_attrib["mime-type"] for prop_attrib in preview if "mime-type" in prop_attrib.keys()}
            if len(mime_types) > 0:
                record = await Holder.get_mime_types(cred_id)
                if record:
                    await sirius_sdk.NonSecrets.delete_wallet_record("mime-types", cred_id)
                await sirius_sdk.NonSecrets.add_wallet_record("mime-types", cred_id, base64.b64encode(json.dumps(mime_types).encode()).decode())

    @staticmethod
    async def get_mime_types(cred_id: str) -> dict:
        try:
            record = await sirius_sdk.NonSecrets.get_wallet_record("mime-types", cred_id, RetrieveRecordOptions(True, True, False))
        except WalletItemNotFound:
            record = None
        if record is not None:
            return json.loads(base64.b64decode(record["value"]).decode())
        else:
            return {}
