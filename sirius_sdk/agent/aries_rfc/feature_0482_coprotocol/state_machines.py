"""We need a standard way for one protocol to invoke another, giving it input, getting its output, detaching, and debugging.
  details:
    - Feature: https://github.com/hyperledger/aries-rfcs/tree/main/features/0482-coprotocol-protocol
    - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols
"""
from enum import Enum
from typing import Optional, Union, List, Dict, Any, Tuple

import sirius_sdk
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.hub.coprotocols import CoProtocolThreadedP2P
from sirius_sdk.abstract.p2p import Pairwise
from sirius_sdk.errors.exceptions import SiriusTimeoutIO

from .messages import CoProtocolBind, CoProtocolAttach, CoProtocolInput, CoProtocolOutput, \
    CoProtocolDetach, CoProtocolProblemReport


class AttachContext(dict):
    pass


class Caller(AbstractStateMachine):
    """The caller role is played by the entity giving input and getting output.
    The called is the entity getting input and giving output.

    see details:
      - https://github.com/hyperledger/aries-rfcs/tree/main/features/0482-coprotocol-protocol
    """

    class State(Enum):
        # https://github.com/hyperledger/aries-rfcs/tree/main/features/0482-coprotocol-protocol#states
        NULL = 'NULL'
        DETACHED = 'DETACHED'
        ATTACHED = 'ATTACHED'
        DONE = 'DONE'

    def __init__(
            self, called: Pairwise, thid: str, pthid: str = None,
            time_to_live: int = None, logger=None, *args, **kwargs
    ):
        """Initialize Caller state-machine environment

        :param called (required): is the entity getting input and giving output
        :param thid (required): co-protocol thread-id
        :param pthid (optional): parent co-protocol thread-id
        :param time_to_live (optional): time the state-machine is alive,
        :param logger (optional): state-machine logger
        """
        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self._problem_report = None
        self.__time_to_live = time_to_live
        self.__called = called
        self.__thid = thid
        self.__pthid = pthid
        self.__state = self.State.NULL
        self.__context: Optional[AttachContext] = None
        self._coprotocol: Optional[CoProtocolThreadedP2P] = None
        self._coprotocol_child: Optional[CoProtocolThreadedP2P] = None
        self._problem_report: Optional[CoProtocolProblemReport] = None

    @property
    def state(self) -> State:
        """Current State"""
        return self.__state

    @property
    def context(self) -> Optional[AttachContext]:
        """Context that was retrieved from [Called] entity after bind"""
        return self.__context

    @property
    def thid(self) -> str:
        """Thread-ID

          see details:
            - https://github.com/hyperledger/aries-rfcs/tree/main/concepts/0008-message-id-and-threading#threaded-messages
        """
        return self.__thid

    @property
    def pthid(self) -> str:
        """Parent Thread-ID

          see details:
            - https://github.com/hyperledger/aries-rfcs/tree/main/concepts/0008-message-id-and-threading#threaded-messages
            - https://github.com/hyperledger/aries-rfcs/tree/main/concepts/0478-coprotocols#coroutines
        """
        return self.__pthid

    @property
    def problem_report(self) -> CoProtocolProblemReport:
        return self._problem_report

    async def bind(
            self, cast: Union[List, Dict] = None, co_binding_id: str = None, **extra_fields
    ) -> (bool, Optional[AttachContext]):
        """The protocol begins with a bind message sent from caller to called.
          This message basically says, "I would like to interact with a new coprotocol instance

        :param cast: (optional) declaring roles and binding context
        :param co_binding_id: (optional) internal [caller-to-called] binding-id
        :param extra_fields: additional bind message fields
        :return: [operation status, context called entity was set]

        See details:
          - https://github.com/hyperledger/aries-rfcs/tree/main/features/0482-coprotocol-protocol#messages
        """
        if self.state != self.State.ATTACHED:
            await self.log(comment='create co-protocol')
            await self._create_coprotocol()
            request = self._build_bind_request(cast, co_binding_id, **extra_fields)
            await self.log(comment='sending bind request', message=request)
            await self._new_state(self.State.DETACHED)
            await self._coprotocol.send(request)
            try:
                while True:
                    response, _, _ = await self._coprotocol.get_one()
                    await self.log(comment='received attach response', message=response)
                    if isinstance(response, CoProtocolAttach):
                        self.__context = AttachContext()
                        for fld, value in response.items():
                            if not (fld.startswith('@') or fld.startswith('~')):
                                self.__context[fld] = value
                        thid = response.thid or response.id
                        await self.log(comment=f'create child co-protocol with thread-id: "thid"')
                        await self._create_child_coprotocol(thid=thid)
                        await self._new_state(self.State.ATTACHED)
                        await self._clean_coprotocol()
                        return True, self.__context
                    elif isinstance(response, CoProtocolProblemReport):
                        self._problem_report = response
                        return False, None
            except SiriusTimeoutIO:
                await self.log(comment='IO timeout occurred')
                return False, None
        else:
            await self.log(comment='already in attached state: nothing to-do')
            return True, None

    async def input(self, data: Any, **extra):
        """The caller can now kick off/invoke the protocol with an input message.

           This allows the caller to invoke the bound coprotocol instance, and to pass it any number of named inputs.
        """

        if self.state == self.State.ATTACHED:
            msg = self._build_input_message(data, **extra)
            msg.thid = self._coprotocol_child.thid
            await self.log(comment='sending input message', message=msg)
            await self._coprotocol_child.send(msg)
        else:
            await self.log(comment='state error')
            raise RuntimeError('CoProtocol must be attached first! Call bind before operate...')

    async def raise_problem(self, problem_code: str, explain: str):
        if self.state == self.State.ATTACHED:
            msg = CoProtocolProblemReport(problem_code=problem_code, explain=explain, thread_id=self.thid)
            msg.thid = self._coprotocol_child.thid
            await self.log(comment='raising problem-report', message=msg)
            await self._coprotocol_child.send(msg)
        else:
            await self.log(comment='state error')
            raise RuntimeError('CoProtocol must be attached first! Call bind before operate...')

    async def wait_output(self) -> Tuple[bool, Any, Optional[Dict]]:
        """Later, when the coprotocol instance wants to emit an output from called to caller, it uses an output message

        :return: [success, Data, extra_fields]
        """
        if self.state == self.State.ATTACHED:
            while True:
                msg, _, _ = await self._coprotocol_child.get_one()
                if isinstance(msg, CoProtocolOutput):
                    await self.log(comment='received output', message=msg)
                    data = msg.pop('data', None)
                    extra_fields = dict()
                    for fld, value in msg.items():
                        if not (fld.startswith('@') or fld.startswith('~')):
                            extra_fields[fld] = value
                    return True, data, extra_fields
                elif isinstance(msg, CoProtocolProblemReport):
                    await self.log(comment='received problem-report', message=msg)
                    self._problem_report = msg
                    return False, None, None
        else:
            await self.log(comment='state error')
            raise RuntimeError('CoProtocol must be attached first! Call bind before operate...')

    async def detach(self):
        """If a caller wants to detach, it uses a detach message.
           This leaves the coprotocol running on called; all inputs that it emits are sent to the bitbucket,
           and it advances on its normal state trajectory as if it were a wholly independent protocol:
        """
        if self.state == self.State.ATTACHED:
            await self.log(comment='detaching...')
            request = self._build_detach_request()
            request.thid = self._coprotocol_child.thid
            await self._coprotocol_child.send(request)
            await self._new_state(self.State.DETACHED)
            self.__context = None
            await self._clean_coprotocol()
            await self._clean_coprotocol_child()
            await self.log(comment='detached!')

    async def done(self):
        if self.state == self.State.ATTACHED:
            await self.log(comment='done protocol')
            await self._new_state(self.State.DONE)
            await self._clean_coprotocol()
            await self._clean_coprotocol_child()

    async def _new_state(self, new_state: State):
        """State transition"""
        if new_state != self.state:
            valid_states = []
            ignore_states = []
            if self.state == self.State.NULL:
                valid_states = [self.State.DETACHED]
                ignore_states = [self.State.DONE]
            elif self.state == self.State.DETACHED:
                valid_states = [self.State.ATTACHED]
                ignore_states = [self.State.DONE]
            elif self.state == self.State.ATTACHED:
                valid_states = [self.State.DONE, self.State.DETACHED]
                ignore_states = [self.State.DONE]
            elif self.state == self.State.DONE:
                valid_states = [self.State.DETACHED]
                ignore_states = []
            if new_state in valid_states:
                await self.log(comment=f'Change status from "{self.__state.value}" to "{new_state.value}"')
                self.__state = new_state
            elif new_state in ignore_states:
                return
            else:
                raise RuntimeError(f'Invalid state transition from "{self.__state.value}" to "{new_state.value}"')

    def _build_bind_request(
            self, cast: Union[List, Dict] = None, co_binding_id: str = None, **extra_fields
    ) -> CoProtocolBind:
        request = CoProtocolBind(
            id_=self.__thid, thid=self.__thid, pthid=self.__pthid, cast=cast, co_binding_id=co_binding_id
        )
        if extra_fields:
            for fld, value in extra_fields.items():
                request[fld] = value
        return request

    def _build_input_message(self, data: Any, **extra) -> CoProtocolInput:
        msg = CoProtocolInput(pthid=self.__thid)
        msg['data'] = data
        for fld, value in extra.items():
            msg[fld] = value
        return msg

    def _build_detach_request(self) -> CoProtocolDetach:
        request = CoProtocolDetach(pthid=self.__thid)
        return request

    async def _create_coprotocol(self) -> CoProtocolThreadedP2P:
        self._coprotocol = CoProtocolThreadedP2P(
            thid=self.__thid,
            to=self.__called,
            pthid=self.__pthid,
            time_to_live=self.time_to_live
        )
        self._register_for_aborting(self._coprotocol)
        return self._coprotocol

    async def _create_child_coprotocol(self, thid: str) -> CoProtocolThreadedP2P:
        self._coprotocol_child = CoProtocolThreadedP2P(
            thid=thid,
            to=self.__called,
            pthid=self.__thid,
            time_to_live=self.time_to_live
        )
        self._register_for_aborting(self._coprotocol_child)
        return self._coprotocol_child

    async def _clean_coprotocol(self):
        if self._coprotocol is not None:
            try:
                await self._coprotocol.clean()
                self._unregister_for_aborting(self._coprotocol)
            finally:
                self._coprotocol = None

    async def _clean_coprotocol_child(self):
        if self._coprotocol_child is not None:
            try:
                await self._coprotocol_child.clean()
                self._unregister_for_aborting(self._coprotocol_child)
            finally:
                self._coprotocol_child = None


class Called(AbstractStateMachine):

    class State(Enum):
        # https://github.com/hyperledger/aries-rfcs/tree/main/features/0482-coprotocol-protocol#states
        NULL = 'NULL'
        ATTACHED = 'ATTACHED'
        DONE = 'DONE'

    class CoProtocolDetachedByCaller(RuntimeError):
        pass

    def __init__(self, *args, **kwargs):
        """Initialize Called state-machine environment

          Do nat create State-Machine with new constructor,
          !! Use OPEN method instead !!
        """
        super().__init__(*args, **kwargs)
        self._problem_report = None
        self._coprotocol: Optional[CoProtocolThreadedP2P] = None
        self.__caller: Optional[Pairwise] = None
        self.__bind_context = None
        self.__context: Optional[AttachContext] = None
        self.__state = self.State.NULL

    @property
    def caller(self) -> Pairwise:
        return self.__caller

    @property
    def context(self) -> Optional[AttachContext]:
        return self.__context

    @property
    def state(self) -> State:
        return self.__state

    @property
    def problem_report(self) -> CoProtocolProblemReport:
        return self._problem_report

    @staticmethod
    async def open(
            caller: Pairwise, request: CoProtocolBind,
            logger=None, *args, **kwargs
    ) -> "Called":
        """The [Called] is the entity getting input and giving output.

        :param caller: Entity who invoke co-protocol
        :param request: initialize message
        :param logger: external logger
        :return: state-machine instance
        """

        inst = Called(
            time_to_live=None,  # called protocol is terminated with caller entity (detach),
            logger=logger,
            *args, **kwargs
        )
        inst.__caller = caller
        inst.__context = AttachContext()
        for fld, value in request.items():
            if not (fld.startswith('@') or fld.startswith('~')):
                inst.__context[fld] = value
        await inst.log(comment='open', message=request)
        await inst._create_coprotocol(thid=request.thid or request.id)
        return inst

    async def attach(self, **fields):
        msg = self._build_attach_message(**fields)
        await self.log(comment='attach', message=msg)
        await sirius_sdk.send_to(msg, to=self.__caller)
        self.__state = self.State.ATTACHED

    async def done(self):
        await self.log(comment='done')
        await self._clean_coprotocol()
        self.__state = self.State.DONE

    async def wait_input(self) -> (bool, Any, Optional[Dict]):
        """Later, when the coprotocol instance wants to emit an output from called to caller, it uses an output message

        :return: [success, Data, extra_fields]
        :raises CoProtocolDetachedByCaller if Caller was called detach
        """
        if self.state == self.State.ATTACHED:
            while True:
                msg, _, _ = await self._coprotocol.get_one()
                if isinstance(msg, CoProtocolInput):
                    await self.log(comment='received input', message=msg)
                    data = msg.pop('data', None)
                    extra_fields = dict()
                    for fld, value in msg.items():
                        if not (fld.startswith('@') or fld.startswith('~')):
                            extra_fields[fld] = value
                    return True, data, extra_fields
                elif isinstance(msg, CoProtocolProblemReport):
                    await self.log(comment='received problem-report', message=msg)
                    self._problem_report = msg
                    return False, None, None
                elif isinstance(msg, CoProtocolDetach):
                    await self.done()
                    raise self.CoProtocolDetachedByCaller('Called entity received DETACH message from Caller')
        else:
            await self.log(comment='state error')
            raise RuntimeError('CoProtocol must be attached first! Call bind before operate...')

    async def output(self, data: Any, **extra):
        """The called can raise output message.
        """

        if self.state == self.State.ATTACHED:
            msg = self._build_output_message(data, **extra)
            msg.thid = self._coprotocol.thid
            await self.log(comment='sending output message', message=msg)
            await self._coprotocol.send(msg)
        else:
            await self.log(comment='state error')
            raise RuntimeError('CoProtocol must be attached first! Call bind before operate...')

    async def raise_problem(self, problem_code: str, explain: str):
        if self.state == self.State.ATTACHED:
            msg = CoProtocolProblemReport(problem_code=problem_code, explain=explain, thread_id=self._coprotocol.thid)
            await self._coprotocol.send(msg)
        else:
            await self.log(comment='state error')
            raise RuntimeError('CoProtocol must be attached first! Call bind before operate...')

    def _build_attach_message(self, **fields) -> CoProtocolAttach:
        msg = CoProtocolAttach(thid=self._coprotocol.thid)
        for fld, value in fields.items():
            msg[fld] = value
        return msg

    def _build_output_message(self, data: Any, **extra) -> CoProtocolOutput:
        msg = CoProtocolOutput(thid=self._coprotocol.thid)
        msg['data'] = data
        for fld, value in extra.items():
            msg[fld] = value
        return msg

    async def _create_coprotocol(self, thid: str) -> CoProtocolThreadedP2P:
        self._coprotocol = CoProtocolThreadedP2P(
            thid=thid,
            to=self.__caller,
            time_to_live=self.time_to_live
        )
        self._register_for_aborting(self._coprotocol)
        return self._coprotocol

    async def _clean_coprotocol(self):
        if self._coprotocol is not None:
            try:
                await self._coprotocol.clean()
                self._unregister_for_aborting(self._coprotocol)
            finally:
                self._coprotocol = None
