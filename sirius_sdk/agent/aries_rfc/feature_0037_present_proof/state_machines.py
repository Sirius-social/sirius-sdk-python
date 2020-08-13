from typing import List, Union
from datetime import datetime, timedelta

from ....agent.pairwise import Pairwise
from ....agent.aries_rfc.utils import utc_to_str
from ....agent.ledger import Schema, CredentialDefinition
from ....errors.indy_exceptions import WalletItemNotFound
from ....agent.wallet.abstract.anoncreds import AbstractAnonCreds
from ....agent.sm import AbstractStateMachine, StateMachineTerminatedWithError
from ..feature_0015_acks import Ack, Status
from .messages import *


PROPOSE_NOT_ACCEPTED = "propose_not_accepted"
RESPONSE_NOT_ACCEPTED = "response_not_accepted"
RESPONSE_PROCESSING_ERROR = "response_processing_error"
REQUEST_NOT_ACCEPTED = "request_not_accepted"
RESPONSE_FOR_UNKNOWN_REQUEST = "response_for_unknown_request"
REQUEST_PROCESSING_ERROR = 'request_processing_error'
VERIFY_ERROR = 'verify_error'


class Verifier(AbstractStateMachine):

    def __init__(
            self, api: AbstractAnonCreds, prover: Pairwise, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.__api = api
        self.__prover = prover
        self.__transport = None
        self.__problem_report = None

    async def verify(
            self, proof_request: dict, translation: List[AttribTranslation] = None,
            comment: str = None, locale: str = BasePresentProofMessage.DEF_LOCALE
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
                    expires_time=utc_to_str(expires_time)
                )
                request_msg.please_ack = True
                resp = await self.__switch(request_msg)
                if not isinstance(resp, PresentationMessage):
                    raise StateMachineTerminatedWithError(
                        RESPONSE_NOT_ACCEPTED, 'Unexpected @type: %s' % str(resp.type)
                    )
            except StateMachineTerminatedWithError as e:
                self.__problem_report = PresentProofProblemReport(e.problem_code, e.explain)
                if e.notify:
                    await self.__send(self.__problem_report)
                return False
            else:
                return True
        finally:
            await self.__stop()

    @property
    def problem_report(self) -> PresentProofProblemReport:
        return self.__problem_report

    @property
    def protocols(self) -> List[str]:
        return [BasePresentProofMessage.PROTOCOL, Ack.PROTOCOL]

    async def __start(self):
        self.__transport = await self.transports.spawn(self.__prover)
        await self.__transport.start(self.protocols, self.time_to_live)

    async def __stop(self):
        if self.__transport:
            await self.__transport.stop()
            self.__transport = None

    async def __switch(self, request: BasePresentProofMessage) -> Union[BasePresentProofMessage, Ack]:
        ok, resp = await self.__transport.switch(request)
        if ok:
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

    def __init__(
            self, api: AbstractAnonCreds, verifier: Pairwise, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.__api = api
        self.__verifier = verifier
        self.__transport = None
        self.__problem_report = None

    @property
    def problem_report(self) -> PresentProofProblemReport:
        return self.__problem_report

    @property
    def protocols(self) -> List[str]:
        return [BasePresentProofMessage.PROTOCOL, Ack.PROTOCOL]

    async def __start(self):
        self.__transport = await self.transports.spawn(self.__verifier)
        await self.__transport.start(self.protocols, self.time_to_live)

    async def __stop(self):
        if self.__transport:
            await self.__transport.stop()
            self.__transport = None

    async def __switch(self, request: BasePresentProofMessage) -> Union[BasePresentProofMessage, Ack]:
        ok, resp = await self.__transport.switch(request)
        if ok:
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
