import base64
import uuid
import contextlib
from typing import Optional, Union

import sirius_sdk
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.abstract.p2p import Pairwise
from sirius_sdk.hub.coprotocols import CoProtocolThreadedP2P
from sirius_sdk.errors.exceptions import StateMachineAborted, OperationAbortedManually, StateMachineTerminatedWithError

from .messages import StreamOperation, StreamOperationResult, ConfidentialStorageMessageProblemReport
from .streams import AbstractReadOnlyStream, AbstractWriteOnlyStream, BaseStreamEncryption
from . import ConfidentialStorageEncType
from .errors import *

PROBLEM_CODE_EOF = 'eof'
PROBLEM_CODE_ENCRYPTION = 'encryption_error'
PROBLEM_CODE_INIT = 'initialization_error'
PROBLEM_CODE_SEEKABLE = 'stream_is_not_seekable'
PROBLEM_CODE_FORMAT = 'format_error'
PROBLEM_CODE_INVALID_REQ = 'invalid_request'
PROBLEM_CODE_TIMEOUT_OCCURRED = 'timeout_occurred'
PROBLEM_CODE_PERMISSION_DENIED = 'permission_denied'


def problem_report_from_exception(e: BaseConfidentialStorageError) -> ConfidentialStorageMessageProblemReport:
    if isinstance(e, StreamEOF):
        problem_code, explain = PROBLEM_CODE_EOF, e.message
    elif isinstance(e, StreamFormatError):
        problem_code, explain = PROBLEM_CODE_FORMAT, e.message
    elif isinstance(e, StreamInitializationError):
        problem_code, explain = PROBLEM_CODE_INIT, e.message
    elif isinstance(e, StreamEncryptionError):
        problem_code, explain = PROBLEM_CODE_ENCRYPTION, e.message
    elif isinstance(e, StreamSeekableError):
        problem_code, explain = PROBLEM_CODE_SEEKABLE, e.message
    elif isinstance(e, ConfidentialStorageTimeoutOccurred):
        problem_code, explain = PROBLEM_CODE_TIMEOUT_OCCURRED, e.message
    elif isinstance(e, ConfidentialStoragePermissionDenied):
        problem_code, explain = PROBLEM_CODE_PERMISSION_DENIED, e.message
    else:
        problem_code, explain = PROBLEM_CODE_INVALID_REQ, e.message
    report = ConfidentialStorageMessageProblemReport(
        problem_code=problem_code, explain=explain
    )
    return report


def exception_from_problem_report(report: ConfidentialStorageMessageProblemReport) -> Optional[Union[BaseConfidentialStorageError, StateMachineTerminatedWithError]]:
    if report.problem_code == PROBLEM_CODE_EOF:
        return StreamEOF(report.explain)
    elif report.problem_code == PROBLEM_CODE_ENCRYPTION:
        return StreamEncryptionError(report.explain)
    elif report.problem_code == PROBLEM_CODE_INIT:
        return StreamInitializationError(report.explain)
    elif report.problem_code == PROBLEM_CODE_SEEKABLE:
        return StreamSeekableError(report.explain)
    elif report.problem_code == PROBLEM_CODE_FORMAT:
        return StreamFormatError(report.explain)
    elif report.problem_code == PROBLEM_CODE_TIMEOUT_OCCURRED:
        return ConfidentialStorageTimeoutOccurred(report.explain)
    elif report.problem_code == PROBLEM_CODE_PERMISSION_DENIED:
        return ConfidentialStoragePermissionDenied(report.explain)
    else:
        return None


class CallerReadOnlyStreamProtocol(AbstractStateMachine, AbstractReadOnlyStream):
    """ReadOnly Stream protocol for Caller entity

    See details:
        - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols
    """

    def __init__(
            self, called: Pairwise, uri: str, read_timeout: int, retry_count: int = 1,
            thid: str = None, enc: BaseStreamEncryption = None, logger=None, *args, **kwargs
    ):
        """Stream abstraction for read-only operations provided with [Vault] entity

        :param called (required): Called entity who must process requests (Vault/Storage/etc)
        :param uri (required): address of stream resource
        :param read_timeout (required): time till operation is timeout occurred
        :param thid (optional): co-protocol thread-id
        :param enc (optional): allow decrypt stream chunks
        :param retry_count (optional): if chunk-read-operation was terminated with timeout
                                       then protocol will re-try operation from the same seek
        :param logger (optional): state-machine logger
        """
        AbstractStateMachine.__init__(self, time_to_live=read_timeout, logger=logger, *args, **kwargs)
        AbstractReadOnlyStream.__init__(self, path=uri, chunks_num=0, enc=enc)
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None
        self.__uri = uri
        self.__called = called
        self.__retry_count = retry_count
        self.__thid = thid or uuid.uuid4().hex
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None

    @property
    def called(self) -> Pairwise:
        return self.__called

    @property
    def thid(self) -> str:
        return self.__thid

    @property
    def read_timeout(self) -> int:
        return self.time_to_live

    @property
    def retry_count(self) -> int:
        return self.__retry_count

    async def open(self):
        resp = await self.rpc(
            request=StreamOperation(
                operation=StreamOperation.OperationCode.OPEN,
                params={
                    'uri': self.__uri,
                    'encrypted': self.enc is not None
                }
            )
        )
        state = resp.params['state']
        self._seekable = state.get('seekable', None)
        self._current_chunk = state.get('current_chunk', 0)
        self._chunks_num: int = state.get('chunks_num', 0)
        self._is_open = True

    async def close(self):
        if self._is_open:
            async with self.coprotocol() as co:
                self._is_open = False
                req = StreamOperation(
                    operation=StreamOperation.OperationCode.CLOSE
                )
                await co.send(req)
                self._current_chunk = 0
                self._chunks_num = 0
                self._seekable = None
            await self.close_coprotocol()

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
        if no is not None:
            before_no = no
        else:
            before_no = self._current_chunk
        no, encrypted = await self.__internal_read_chunk(before_no)
        chunk = await self.decrypt(encrypted)
        return no, chunk

    async def eof(self) -> bool:
        return self._current_chunk >= self._chunks_num

    async def open_coprotocol(self) -> sirius_sdk.CoProtocolThreadedP2P:
        if self.__coprotocol is None:
            self.__coprotocol = sirius_sdk.CoProtocolThreadedP2P(
                thid=self.thid,
                to=self.called,
                time_to_live=self.read_timeout
            )
            self._register_for_aborting(self.__coprotocol)
        return self.__coprotocol

    async def close_coprotocol(self):
        if self.__coprotocol:
            await self.__coprotocol.clean()
            self._unregister_for_aborting(self.__coprotocol)
            self.__coprotocol = None

    @contextlib.asynccontextmanager
    async def coprotocol(self):
        co = await self.open_coprotocol()
        try:
            yield co
        except OperationAbortedManually:
            await self.log(progress=100, message='Aborted')
            raise StateMachineAborted('Aborted by User')

    async def rpc(self, request: StreamOperation) -> StreamOperationResult:
        async with self.coprotocol() as co:
            while True:
                success, resp = await co.switch(request)
                if success:
                    if isinstance(resp, StreamOperationResult):
                        return resp
                    elif isinstance(resp, ConfidentialStorageMessageProblemReport):
                        self._problem_report = resp
                        exc = exception_from_problem_report(resp)
                        if exc:
                            raise exc
                        else:
                            raise StateMachineTerminatedWithError(problem_code=resp.problem_code, explain=resp.explain)
                    else:
                        # Co-Protocol will terminate if timeout occurred
                        pass
                else:
                    err_message = 'Caller read operation timeout occurred!'
                    report = ConfidentialStorageMessageProblemReport(
                        problem_code=PROBLEM_CODE_TIMEOUT_OCCURRED,
                        explain=err_message
                    )
                    await co.send(report)
                    raise ConfidentialStorageTimeoutOccurred(err_message)

    async def __internal_read_chunk(self, read_chunk: int) -> (int, bytes):
        before_no = read_chunk
        after_no = read_chunk + 1
        for n in range(self.retry_count):
            try:
                resp = await self.rpc(
                    request=StreamOperation(
                        operation=StreamOperation.OperationCode.READ_CHUNK,
                        params={
                            'no': before_no
                        }
                    )
                )
            except ConfidentialStorageTimeoutOccurred:
                # Next iteration
                await self.close_coprotocol()
                continue
            no = resp.params['no']
            if no == after_no:
                chunk = base64.b64decode(resp.params['chunk'])
                self._current_chunk = no
                return no, chunk
            else:
                # re-try again
                pass
        raise ConfidentialStorageTimeoutOccurred(
            f'Stream read Timeout occurred for timeout={self.read_timeout} and retry_count={self.retry_count}'
        )


class CalledReadOnlyStreamProtocol(AbstractStateMachine):
    """ReadOnly Stream protocol for Called entity, Called entity most probably operate on Vault side
       Acts as proxy to physical stream implementation

    See details:
        - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols
    """

    def __init__(
            self, caller: Pairwise, thid: str = None, time_to_live: int = None, logger=None, *args, **kwargs
    ):
        """Setup stream proxy environment

        :param caller: Caller of stream resource operations
        :param thid (optional): co-protocol thread-id
        :param time_to_live (optional): time the state-machine is alive,
        :param logger (optional): state-machine logger
        """
        super(CalledReadOnlyStreamProtocol, self).__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self.__caller: Pairwise = caller
        self.__thid = thid
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None

    @property
    def caller(self) -> Pairwise:
        return self.__caller

    @property
    def thid(self) -> str:
        return self.__thid

    async def run_forever(self, proxy_to: AbstractReadOnlyStream, exit_on_close: bool = True):
        """Proxy requests in loop

        :param proxy_to: stream interface implementation
        :param exit_on_close: (bool) exit loop on close
        :return:
        """
        try:
            async with self.coprotocol(close_on_exit=True) as co:
                while True:
                    request, sender_verkey, recipient_verkey = await co.get_one()
                    await self.handle(request, proxy_to)
                    if isinstance(request, StreamOperation):
                        if request.operation == StreamOperation.OperationCode.CLOSE and exit_on_close:
                            return
        finally:
            if self.__coprotocol:
                await self.close_coprotocol()

    async def handle(
            self, request: Union[StreamOperation, ConfidentialStorageMessageProblemReport],
            proxy_to: AbstractReadOnlyStream
    ):
        if isinstance(request, ConfidentialStorageMessageProblemReport):
            self._problem_report = request
        elif isinstance(request, StreamOperation):
            co = await self.open_coprotocol()
            try:
                if request.operation == StreamOperation.OperationCode.OPEN:
                    encrypted = request.params.get('encrypted', False)
                    if encrypted:
                        # Local stream must persist chunks structure
                        if proxy_to.enc is None:
                            proxy_to.enc = BaseStreamEncryption(type_=ConfidentialStorageEncType.UNKNOWN)
                    await proxy_to.open()
                    params = {
                        'state': {
                            'seekable': proxy_to.seekable,
                            'chunks_num': proxy_to.chunks_num,
                            'current_chunk': proxy_to.current_chunk,
                        }
                    }
                    await co.send(StreamOperationResult(request.operation, params))
                elif request.operation == StreamOperation.OperationCode.CLOSE:
                    await proxy_to.close()
                elif request.operation == StreamOperation.OperationCode.SEEK_TO_CHUNK:
                    no = request.params.get('no')
                    new_no = await proxy_to.seek_to_chunk(no)
                    params = {'no': new_no}
                    await co.send(StreamOperationResult(request.operation, params))
                elif request.operation == StreamOperation.OperationCode.READ_CHUNK:
                    no = request.params.get('no')
                    new_no, chunk = await proxy_to.read_chunk(no)
                    chunk = base64.b64encode(chunk).decode()
                    params = {'no': new_no, 'chunk': chunk}
                    await co.send(StreamOperationResult(request.operation, params))
            except BaseConfidentialStorageError as e:
                report = problem_report_from_exception(e)
                # Don't raise any error: give caller to make decision
                await co.send(report)

    async def open_coprotocol(self) -> sirius_sdk.CoProtocolThreadedP2P:
        if self.__coprotocol is None:
            self.__coprotocol = sirius_sdk.CoProtocolThreadedP2P(
                thid=self.__thid,
                to=self.caller,
                time_to_live=self.time_to_live
            )
            self._register_for_aborting(self.__coprotocol)
        return self.__coprotocol

    async def close_coprotocol(self):
        if self.__coprotocol:
            await self.__coprotocol.clean()
            self._unregister_for_aborting(self.__coprotocol)
            self.__coprotocol = None

    @contextlib.asynccontextmanager
    async def coprotocol(self, close_on_exit: bool = False):
        co = await self.open_coprotocol()
        try:
            try:
                yield co
            except OperationAbortedManually:
                await self.log(progress=100, message='Aborted')
                raise StateMachineAborted('Aborted by User')
        finally:
            if close_on_exit:
                await self.close_coprotocol()


class CallerWriteOnlyStreamProtocol(AbstractStateMachine, AbstractWriteOnlyStream):
    """WriteOnly Stream protocol for Caller entity

    See details:
        - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols
    """

    def __init__(
            self, called: Pairwise, uri: str, thid: str = None, enc: BaseStreamEncryption = None,
            retry_count: int = 3, time_to_live: int = 60, logger=None, *args, **kwargs
    ):
        """Stream abstraction for write-only operations provided with [Vault] entity

        :param called (required): Called entity who must process requests (Vault/Storage/etc)
        :param uri (required): address of stream resource
        :param thid (optional): co-protocol thread-id
        :param enc: allow encrypt stream chunks
        :param retry_count (optional): if chunk-write-operation was terminated with timeout
                                       then protocol will re-try operation from the same seek
        :param logger (optional): state-machine logger
        """

        AbstractStateMachine.__init__(self, time_to_live=time_to_live, logger=logger, *args, **kwargs)
        AbstractWriteOnlyStream.__init__(self, path=uri, enc=enc)
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None
        self.__uri = uri
        self.__called = called
        self.__retry_count = retry_count
        self.__thid = thid or uuid.uuid4().hex
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None

    @property
    def called(self) -> Pairwise:
        return self.__called

    @property
    def thid(self) -> str:
        return self.__thid

    @property
    def retry_count(self) -> int:
        return self.__retry_count

    async def open(self):
        resp = await self.rpc(
            request=StreamOperation(
                operation=StreamOperation.OperationCode.OPEN,
                params={
                    'uri': self.__uri,
                    'encrypted': self.enc is not None
                }
            )
        )
        state = resp.params['state']
        self._seekable = state.get('seekable', None)
        self._current_chunk = state.get('current_chunk', 0)
        self._chunks_num = state.get('chunks_num', 0)
        self.chunk_size = state.get('chunk_size', 0)
        self._is_open = True

    async def close(self):
        if self._is_open:
            async with self.coprotocol() as co:
                self._is_open = False
                req = StreamOperation(
                    operation=StreamOperation.OperationCode.CLOSE
                )
                await co.send(req)
                self._current_chunk = 0
                self._chunks_num = 0
                self._seekable = None
            await self.close_coprotocol()

    async def write_chunk(self, chunk: bytes, no: int = None) -> (int, int):
        if no is not None:
            before_no = no
        else:
            before_no = self._current_chunk
        encrypted = await self.encrypt(chunk)
        no, chunk = await self.__internal_write_chunk(before_no, encrypted)
        return no, chunk

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

    async def truncate(self, no: int = 0):
        resp = await self.rpc(
            request=StreamOperation(
                operation=StreamOperation.OperationCode.TRUNCATE,
                params={
                    'no': no
                }
            )
        )
        state = resp.params['state']
        self._current_chunk = state.get('current_chunk', self.current_chunk)
        self._chunks_num = state.get('chunks_num', self.chunks_num)

    async def open_coprotocol(self) -> sirius_sdk.CoProtocolThreadedP2P:
        if self.__coprotocol is None:
            self.__coprotocol = sirius_sdk.CoProtocolThreadedP2P(
                thid=self.thid,
                to=self.called,
                time_to_live=self.time_to_live
            )
            self._register_for_aborting(self.__coprotocol)
        return self.__coprotocol

    async def close_coprotocol(self):
        if self.__coprotocol:
            await self.__coprotocol.clean()
            self._unregister_for_aborting(self.__coprotocol)
            self.__coprotocol = None

    @contextlib.asynccontextmanager
    async def coprotocol(self):
        co = await self.open_coprotocol()
        try:
            yield co
        except OperationAbortedManually:
            await self.log(progress=100, message='Aborted')
            raise StateMachineAborted('Aborted by User')

    async def rpc(self, request: StreamOperation) -> StreamOperationResult:
        async with self.coprotocol() as co:
            while True:
                success, resp = await co.switch(request)
                if success:
                    if isinstance(resp, StreamOperationResult):
                        return resp
                    elif isinstance(resp, ConfidentialStorageMessageProblemReport):
                        self._problem_report = resp
                        if resp.problem_code == PROBLEM_CODE_EOF:
                            raise StreamEOF(resp.explain)
                        elif resp.problem_code == PROBLEM_CODE_ENCRYPTION:
                            raise StreamEncryptionError(resp.explain)
                        elif resp.problem_code == PROBLEM_CODE_INIT:
                            raise StreamInitializationError(resp.explain)
                        elif resp.problem_code == PROBLEM_CODE_SEEKABLE:
                            raise StreamSeekableError(resp.explain)
                        elif resp.problem_code == PROBLEM_CODE_FORMAT:
                            raise StreamFormatError(resp.explain)
                        else:
                            raise StateMachineTerminatedWithError(problem_code=resp.problem_code, explain=resp.explain)
                    else:
                        # Co-Protocol will terminate if timeout occurred
                        pass
                else:
                    err_message = 'Caller write operation timeout occurred!'
                    report = ConfidentialStorageMessageProblemReport(
                        problem_code=PROBLEM_CODE_TIMEOUT_OCCURRED,
                        explain=err_message
                    )
                    await co.send(report)
                    raise ConfidentialStorageTimeoutOccurred(err_message)

    async def __internal_write_chunk(self, chunk_no: int, chunk: bytes) -> (int, int):
        before_no = chunk_no
        chunk_b64 = base64.b64encode(chunk).decode()
        for n in range(self.retry_count):
            try:
                resp = await self.rpc(
                    request=StreamOperation(
                        operation=StreamOperation.OperationCode.WRITE_CHUNK,
                        params={
                            'no': before_no,
                            'chunk': chunk_b64
                        }
                    )
                )
            except ConfidentialStorageTimeoutOccurred:
                # Next iteration
                await self.close_coprotocol()
                continue
            new_offset = resp.params['no']
            writen_sz = resp.params['size']
            self._current_chunk = new_offset
            return new_offset, writen_sz
        raise ConfidentialStorageTimeoutOccurred(
            f'Stream write Timeout occurred for timeout={self.time_to_live} and retry_count={self.retry_count}'
        )


class CalledWriteOnlyStreamProtocol(AbstractStateMachine):
    """
        Called entity on WriteOnly Stream side, Called entity most probably operate on Vault side
        Acts as proxy to physical stream implementation

    See details:
        - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols
    """

    def __init__(
            self, caller: Pairwise, thid: str = None, time_to_live: int = None, logger=None, *args, **kwargs
    ):
        """Setup stream proxy environment

        :param caller: Caller of stream resource operations
        :param thid (optional): co-protocol thread-id
        :param time_to_live (optional): time the state-machine is alive,
        :param logger (optional): state-machine logger
        """
        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self.__caller: Pairwise = caller
        self.__thid = thid
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None

    @property
    def caller(self) -> Pairwise:
        return self.__caller

    @property
    def thid(self) -> str:
        return self.__thid

    async def run_forever(self, proxy_to: AbstractWriteOnlyStream, exit_on_close: bool = True):
        """Proxy requests in loop

        :param proxy_to: stream interface implementation
        :param exit_on_close: (bool) exit loop on close
        :return:
        """
        try:
            async with self.coprotocol(close_on_exit=True) as co:
                while True:
                    request, sender_verkey, recipient_verkey = await co.get_one()
                    await self.handle(request, proxy_to)
                    if isinstance(request, StreamOperation):
                        if request.operation == StreamOperation.OperationCode.CLOSE and exit_on_close:
                            return
        finally:
            if self.__coprotocol:
                await self.close_coprotocol()

    async def handle(
            self, request: Union[StreamOperation, ConfidentialStorageMessageProblemReport],
            proxy_to: AbstractWriteOnlyStream
    ):
        if isinstance(request, ConfidentialStorageMessageProblemReport):
            self._problem_report = request
            exc = exception_from_problem_report(request)
            if exc:
                raise exc
            else:
                raise StateMachineTerminatedWithError(problem_code=request.problem_code, explain=request.explain)
        elif isinstance(request, StreamOperation):
            co = await self.open_coprotocol()
            try:
                if request.operation == StreamOperation.OperationCode.OPEN:
                    encrypted = request.params.get('encrypted', False)
                    if encrypted:
                        # Local stream must persist chunks structure
                        if proxy_to.enc is None:
                            proxy_to.enc = BaseStreamEncryption(type_=ConfidentialStorageEncType.UNKNOWN)
                    await proxy_to.open()
                    params = {
                        'state': {
                            'seekable': proxy_to.seekable,
                            'chunks_num': proxy_to.chunks_num,
                            'current_chunk': proxy_to.current_chunk,
                            'chunk_size': proxy_to.chunk_size
                        }
                    }
                    await co.send(StreamOperationResult(request.operation, params))
                elif request.operation == StreamOperation.OperationCode.CLOSE:
                    await proxy_to.close()
                elif request.operation == StreamOperation.OperationCode.SEEK_TO_CHUNK:
                    no = request.params.get('no')
                    new_no = await proxy_to.seek_to_chunk(no)
                    params = {'no': new_no}
                    await co.send(StreamOperationResult(request.operation, params))
                elif request.operation == StreamOperation.OperationCode.WRITE_CHUNK:
                    no = request.params.get('no')
                    chunk = base64.b64decode(request.params.get('chunk'))
                    new_no, writen_sz = await proxy_to.write_chunk(chunk, no)
                    params = {'no': new_no, 'size': writen_sz}
                    await co.send(StreamOperationResult(request.operation, params))
                elif request.operation == StreamOperation.OperationCode.TRUNCATE:
                    no = request.params.get('no')
                    await proxy_to.truncate(no)
                    params = {
                        'state': {
                            'chunks_num': proxy_to.chunks_num,
                            'current_chunk': proxy_to.current_chunk
                        }
                    }
                    await co.send(StreamOperationResult(request.operation, params))
            except BaseConfidentialStorageError as e:
                report = problem_report_from_exception(e)
                # Don't raise any error: give caller to make decision
                await co.send(report)

    async def open_coprotocol(self) -> sirius_sdk.CoProtocolThreadedP2P:
        if self.__coprotocol is None:
            self.__coprotocol = sirius_sdk.CoProtocolThreadedP2P(
                thid=self.__thid,
                to=self.caller,
                time_to_live=self.time_to_live
            )
            self._register_for_aborting(self.__coprotocol)
        return self.__coprotocol

    async def close_coprotocol(self):
        if self.__coprotocol:
            await self.__coprotocol.clean()
            self._unregister_for_aborting(self.__coprotocol)
            self.__coprotocol = None

    @contextlib.asynccontextmanager
    async def coprotocol(self, close_on_exit: bool = False):
        co = await self.open_coprotocol()
        try:
            try:
                yield co
            except OperationAbortedManually:
                await self.log(progress=100, message='Aborted')
                raise StateMachineAborted('Aborted by User')
        finally:
            if close_on_exit:
                await self.close_coprotocol()


class CallerEncryptedDataVault(AbstractStateMachine):
    pass


class CalledEncryptedDataVault(AbstractStateMachine):
    pass
