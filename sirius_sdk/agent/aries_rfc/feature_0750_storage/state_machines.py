import base64
import uuid
import contextlib
from enum import Enum
from typing import Optional, Union, List, Dict, Any, Tuple

import sirius_sdk
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk import CoProtocolThreadedP2P
from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.errors.exceptions import StateMachineAborted, OperationAbortedManually, StateMachineTerminatedWithError
from sirius_sdk.errors.exceptions import SiriusTimeoutIO

from .messages import StreamOperation, StreamOperationResult, ConfidentialStorageMessageProblemReport
from .streams import AbstractReadOnlyStream, AbstractWriteOnlyStream


class CallerReadOnlyStreamProtocol(AbstractStateMachine, AbstractReadOnlyStream):
    """ReadOnly Stream protocol for Caller entity

    See details:
        - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols
    """

    def __init__(
            self, called: Pairwise, uri: str,
            thid: str = None, time_to_live: int = None, logger=None, *args, **kwargs
    ):
        """Stream abstraction for read-only operations provided with [Vault] entity

        :param called (required): Called entity who must process requests (Vault/Storage/etc)
        :param uri (required): address of stream resource
        :param thid (optional): co-protocol thread-id
        :param time_to_live (optional): time the state-machine is alive,
        :param logger (optional): state-machine logger
        """
        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None
        self.__uri = uri
        self.__time_to_live = time_to_live
        self.__called = called
        self.__thid = thid or uuid.uuid4().hex

    async def open(self):
        resp = await self.rpc(
            request=StreamOperation(
                operation=StreamOperation.OperationCode.OPEN,
                params={
                    'uri': self.__uri
                }
            )
        )
        state = resp.params['state']
        self._seekable = state.get('seekable', None)
        self._current_chunk = state.get('current_chunk', 0)
        self._chunks_num: int = state.get('chunks_num', 0)

    async def close(self):
        async with self.coprotocol() as co:
            req = StreamOperation(
                operation=StreamOperation.OperationCode.CLOSE
            )
            await co.send(req)

    async def seek_to_chunk(self, no: int) -> int:
        resp = await self.rpc(
            request=StreamOperation(
                operation=StreamOperation.OperationCode.SEEK_TO_CHUNK,
                params={
                    'no': no
                }
            )
        )
        no = resp.params['no']
        self._current_chunk = no
        return no

    async def read_chunk(self, no: int = None) -> (int, bytes):
        resp = await self.rpc(
            request=StreamOperation(
                operation=StreamOperation.OperationCode.READ_CHUNK,
                params={
                    'no': no
                }
            )
        )
        no = resp.params['no']
        chunk = base64.b64decode(resp.params['chunk'])
        self._current_chunk = no
        return no, chunk

    async def eof(self) -> bool:
        return self._current_chunk >= self._chunks_num

    @contextlib.asynccontextmanager
    async def coprotocol(self):
        co = sirius_sdk.CoProtocolThreadedP2P(
            thid=self.__thid,
            to=self.__called,
            time_to_live=self.time_to_live
        )
        self._register_for_aborting(co)
        try:
            try:
                yield co
            except OperationAbortedManually:
                await self.log(progress=100, message='Aborted')
                raise StateMachineAborted('Aborted by User')
        finally:
            await co.clean()
            self._unregister_for_aborting(co)

    async def rpc(self, request: StreamOperation) -> StreamOperationResult:
        async with self.coprotocol() as co:
            while True:
                success, resp = await co.switch(request)
                if success:
                    if isinstance(resp, StreamOperationResult):
                        return resp
                    elif isinstance(resp, ConfidentialStorageMessageProblemReport):
                        self._problem_report = resp
                        raise StateMachineTerminatedWithError(problem_code=resp.problem_code, explain=resp.explain)
                    else:
                        # Co-Protocol will terminate if timeout occurred
                        pass
                else:
                    raise StateMachineTerminatedWithError(problem_code='1', explain='')


class CalledReadOnlyStreamProtocol(AbstractStateMachine):
    """ReadOnly Stream protocol for Called entity, Called entity most probably operate on Vault side
       Acts as proxy to physical stream implementation

    See details:
        - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols
    """

    def __init__(
            self, thid: str = None, time_to_live: int = None, logger=None, *args, **kwargs
    ):
        """Setup stream proxy environment

        :param thid (optional): co-protocol thread-id
        :param time_to_live (optional): time the state-machine is alive,
        :param logger (optional): state-machine logger
        """
        super(CalledReadOnlyStreamProtocol, self).__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self.__thid = thid
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None

    async def run_forever(self, caller: Pairwise, proxy_to: AbstractReadOnlyStream, exit_on_close: bool = True):
        """Proxy requests in loop

        :param caller: Caller of stream resource operations
        :param proxy_to: stream interface implementation
        :param exit_on_close: (bool) exit loop on close
        :return:
        """
        async with self.coprotocol(caller) as co:
            while True:
                req, sender_verkey, recipient_verkey = await co.get_one()
                if isinstance(req, ConfidentialStorageMessageProblemReport):
                    self._problem_report = req
                    raise StateMachineTerminatedWithError(problem_code=req.problem_code, explain=req.explain)
                elif isinstance(req, StreamOperation):
                    if req.operation == StreamOperation.OperationCode.OPEN:
                        await proxy_to.open()
                        params = {
                            'state': {
                                'seekable': proxy_to.seekable,
                                'chunks_num': proxy_to.chunks_num,
                                'current_chunk': proxy_to.current_chunk,
                            }
                        }
                        await co.send(StreamOperationResult(req.operation, params))
                    elif req.operation == StreamOperation.OperationCode.CLOSE:
                        await proxy_to.close()
                        if exit_on_close:
                            return
                    elif req.operation == StreamOperation.OperationCode.SEEK_TO_CHUNK:
                        no = req.params.get('no')
                        new_no = await proxy_to.seek_to_chunk(no)
                        params = {'no': new_no}
                        await co.send(StreamOperationResult(req.operation, params))
                    elif req.operation == StreamOperation.OperationCode.READ_CHUNK:
                        no = req.params.get('no')
                        new_no, chunk = await proxy_to.read_chunk(no)
                        chunk = base64.b64encode(chunk).decode()
                        params = {'no': new_no, 'chunk': chunk}
                        await co.send(StreamOperationResult(req.operation, params))
        pass

    @contextlib.asynccontextmanager
    async def coprotocol(self, caller: Pairwise):
        co = sirius_sdk.CoProtocolThreadedP2P(
            thid=self.__thid,
            to=caller,
            time_to_live=self.time_to_live
        )
        self._register_for_aborting(co)
        try:
            try:
                yield co
            except OperationAbortedManually:
                await self.log(progress=100, message='Aborted')
                raise StateMachineAborted('Aborted by User')
        finally:
            await co.clean()
            self._unregister_for_aborting(co)


class WriteOnlyStreamProtocol(AbstractStateMachine, AbstractWriteOnlyStream):
    """
    """

    def __init__(
            self, vault: Pairwise, uri: str,
            thid: str = None, time_to_live: int = None, logger=None, *args, **kwargs
    ):
        """Stream abstraction for read-only operations provided with [Vault] entity"""

        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)

    async def open(self):
        pass

    async def close(self):
        pass

    async def seek(self, pos: int) -> int:
        pass
