import base64
import json
import logging
import uuid
import contextlib
from typing import Optional, Union, List

import sirius_sdk
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.abstract.p2p import Pairwise
from sirius_sdk.hub.coprotocols import CoProtocolThreadedP2P
from sirius_sdk.errors.exceptions import StateMachineAborted, OperationAbortedManually, StateMachineTerminatedWithError

from .components import EncryptedDataVault, VaultConfig
from .messages import *
from .streams import AbstractReadOnlyStream, AbstractWriteOnlyStream, BaseStreamEncryption
from . import ConfidentialStorageEncType, EncryptedDocument, StructuredDocument
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
    elif isinstance(e, EncryptionError):
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
        return EncryptionError(report.explain)
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
        self.__stream_is_open = False
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None

    @property
    def caller(self) -> Pairwise:
        return self.__caller

    @property
    def thid(self) -> str:
        return self.__thid

    @property
    def stream_is_open(self) -> bool:
        return self.__stream_is_open

    @stream_is_open.setter
    def stream_is_open(self, value: bool):
        self.__stream_is_open = value

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
                if proxy_to.is_open != self.stream_is_open:
                    if self.stream_is_open:
                        await proxy_to.open()
                    else:
                        await proxy_to.close()
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
                    self.stream_is_open = True
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
                            raise EncryptionError(resp.explain)
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
        self.__stream_is_open = False
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None

    @property
    def caller(self) -> Pairwise:
        return self.__caller

    @property
    def thid(self) -> str:
        return self.__thid

    @property
    def stream_is_open(self) -> bool:
        return self.__stream_is_open

    @stream_is_open.setter
    def stream_is_open(self, value: bool):
        self.__stream_is_open = value

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
                if proxy_to.is_open != self.stream_is_open:
                    if self.stream_is_open:
                        await proxy_to.open()
                    else:
                        await proxy_to.close()
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
                    self.stream_is_open = True
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


class CallerEncryptedDataVault(AbstractStateMachine, EncryptedDataVault):

    def __init__(
            self, called: Pairwise, read_timeout: int = 30,
            retry_count: int = 3, logger=None, *args, **kwargs
    ):
        """Stream abstraction for write-only operations provided with [Vault] entity

        :param called (required): Called entity who must process requests
        :param uri (required): address of stream resource
        :param thid (optional): co-protocol thread-id
        :param read_timeout (optional): time till read-operation is timeout occurred
        :param retry_count (optional): if chunk-write-operation was terminated with timeout
                                       then protocol will re-try operation from the same seek
        :param logger (optional): state-machine logger
        """
        AbstractStateMachine.__init__(self, time_to_live=None, logger=logger, *args, **kwargs)
        EncryptedDataVault.__init__(self)
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None
        self.__thid: Optional[str] = None
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None
        self.__called = called
        self.__current_vault: Optional[str] = None

    @property
    def thid(self) -> Optional[str]:
        return self.__thid

    @property
    def is_open(self) -> bool:
        return self.__coprotocol is not None

    @property
    def called(self) -> Pairwise:
        return self.__called

    def select(self, vault: str):
        self.__current_vault = vault

    async def open(self):
        if self.__current_vault is None:
            raise RuntimeError('You should select vault (query list of ones at first)!')
        if self.is_open:
            raise RuntimeError('state machine already open! Close it before to start new session')
        session_id = uuid.uuid4().hex
        self.__thid = f'vault[{self.__current_vault}]/{session_id}'
        await self._open_coprotocol()
        await self._rpc(request=DataVaultOpen(vault=self.__current_vault))

    async def close(self):
        await self._close_coprotocol()

    async def list_vaults(self) -> List[VaultConfig]:
        resp = await self._request(request=DataVaultQueryList())
        if isinstance(resp, DataVaultResponseList):
            return resp.vaults
        elif isinstance(resp, ConfidentialStorageMessageProblemReport):
            raise StateMachineTerminatedWithError(resp.problem_code, resp.explain)
        else:
            raise RuntimeError(f'Unexpected response type: {resp.__class__.__name__}')

    async def indexes(self) -> EncryptedDataVault.Indexes:
        pass

    async def create_stream(self, uri: str, meta: dict = None, chunk_size: int = None, **attributes) -> StructuredDocument:
        resp = await self._rpc(
            request=DataVaultCreateStream(uri=uri, meta=meta, chunk_size=chunk_size, attributes=attributes)
        )
        if isinstance(resp, StructuredDocumentMessage):
            attach = resp.documents[0]
            doc = self.__extract_structured_doc(attach)
            return doc
        else:
            raise ConfidentialStorageUnexpectedMessageType(resp)

    async def create_document(self, uri: str, meta: dict = None, **attributes) -> StructuredDocument:
        resp = await self._rpc(
            request=DataVaultCreateDocument(uri=uri, meta=meta, attributes=attributes)
        )
        if isinstance(resp, StructuredDocumentMessage):
            attach = resp.documents[0]
            doc = self.__extract_structured_doc(attach)
            return doc
        else:
            raise ConfidentialStorageUnexpectedMessageType(resp)

    async def update(self, uri: str, meta: dict = None, **attributes):
        await self._rpc(
            request=DataVaultUpdateResource(uri=uri, meta=meta, attributes=attributes)
        )

    async def load(self, uri: str) -> StructuredDocument:
        resp = await self._rpc(
            request=DataVaultLoadResource(uri=uri)
        )
        if isinstance(resp, StructuredDocumentMessage):
            attach = resp.documents[0]
            doc = self.__extract_structured_doc(attach)
            return doc
        else:
            raise ConfidentialStorageUnexpectedMessageType(resp)

    async def save_document(self, uri: str, doc: EncryptedDocument):
        pass

    async def readable(self, uri: str) -> AbstractReadOnlyStream:
        pass

    async def writable(self, uri: str) -> AbstractWriteOnlyStream:
        pass

    async def _request(self, request: BaseDataVaultOperation) -> BaseConfidentialStorageMessage:
        co = sirius_sdk.CoProtocolP2P(
            pairwise=self.called,
            protocols=[BaseDataVaultOperation.PROTOCOL],
            time_to_live=15
        )
        await co.start()
        try:
            ok, resp = await co.switch(request)
            if ok:
                return resp
            else:
                err_message = 'Caller write operation timeout occurred!'
                report = ConfidentialStorageMessageProblemReport(
                    problem_code=PROBLEM_CODE_TIMEOUT_OCCURRED,
                    explain=err_message
                )
                await co.send(report)
                raise ConfidentialStorageTimeoutOccurred(err_message)
        finally:
            await co.stop()

    async def _rpc(self, request: BaseDataVaultOperation) -> Union[BaseDataVaultOperation, DataVaultOperationAck, StructuredDocumentMessage]:
        if not self.is_open:
            raise RuntimeError('Open Vault at first!')
        async with self._coprotocol() as co:
            while True:
                success, resp = await co.switch(request)
                if success:
                    if isinstance(resp, BaseDataVaultOperation) or isinstance(resp, DataVaultOperationAck) or isinstance(resp, StructuredDocumentMessage):
                        return resp
                    elif isinstance(resp, ConfidentialStorageMessageProblemReport):
                        self._problem_report = resp
                        raise StateMachineTerminatedWithError(resp.problem_code, resp.explain, notify=False)
                    else:
                        raise ConfidentialStorageUnexpectedMessageType(resp)
                else:
                    err_message = 'Caller write operation timeout occurred!'
                    raise ConfidentialStorageTimeoutOccurred(err_message)

    async def _open_coprotocol(self) -> sirius_sdk.CoProtocolThreadedP2P:
        if self.__coprotocol is None:
            self.__coprotocol = sirius_sdk.CoProtocolThreadedP2P(
                thid=self.__thid,
                to=self.__called,
                time_to_live=self.time_to_live
            )
            self._register_for_aborting(self.__coprotocol)
        return self.__coprotocol

    async def _close_coprotocol(self):
        if self.__coprotocol:
            await self.__coprotocol.clean()
            self._unregister_for_aborting(self.__coprotocol)
            self.__coprotocol = None

    @contextlib.asynccontextmanager
    async def _coprotocol(self, close_on_exit: bool = False):
        co = await self._open_coprotocol()
        try:
            try:
                yield co
            except OperationAbortedManually:
                await self.log(progress=100, message='Aborted')
                raise StateMachineAborted('Aborted by User')
        finally:
            if close_on_exit:
                await self._close_coprotocol()

    @staticmethod
    def __extract_structured_doc(attach: StructuredDocumentAttach) -> StructuredDocument:
        doc = StructuredDocument(
            id_=attach.id,
            urn=attach.urn,
            meta=attach.meta,
            indexed=[
                StructuredDocument.Index(
                    sequence=ind.sequence,
                    hmac=ind.hmac,
                    attributes=ind.attributes
                )
                for ind in attach.indexed
            ]
        )
        return doc


class CalledEncryptedDataVault(AbstractStateMachine):

    def __init__(self, caller: Pairwise, proxy_to: List[EncryptedDataVault], logger=None, *args, **kwargs):
        """Setup proxy environment

        :param thid (optional): co-protocol thread-id
        :param logger (optional): state-machine logger
        """
        super().__init__(time_to_live=None, logger=logger, *args, **kwargs)
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None
        self.__proxy_to = proxy_to
        self.__caller = caller
        self.__sessions: Dict[str, EncryptedDataVault] = {}
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None

    @property
    def caller(self) -> Pairwise:
        return self.__caller

    @property
    def proxy_to(self) -> List[EncryptedDataVault]:
        return self.__proxy_to

    async def handle(self, request: BaseConfidentialStorageMessage):
        if isinstance(request, ConfidentialStorageMessageProblemReport):
            # Process problem-report
            self._problem_report = request
            logging.warning(
                f'Received problem report problem_code: "{request.problem_code}" explain: "{request.explain}"'
            )
        elif isinstance(request, DataVaultQueryList):
            # Process query of list of available Vaults
            response = DataVaultResponseList(vaults=[vault.cfg for vault in self.proxy_to])
            sirius_sdk.prepare_response(request, response)
            await sirius_sdk.send_to(response, self.caller)
        elif isinstance(request, BaseDataVaultOperation):
            # Process Vault operation
            thread = request.thread
            if thread is None or not thread.thid:
                raise ConfidentialStorageInvalidRequest(
                    'Data Vault request should have "~thread.thid" attribute to bind sessions'
                )
            if isinstance(request, DataVaultOpen):
                # Request to open
                if not request.vault:
                    raise ConfidentialStorageInvalidRequest('You should set "vault" attribute')
                proxy_to = [
                    vault for vault in self.proxy_to
                    if vault.cfg.id == request.vault or vault.cfg.reference_id == request.vault
                ]
                if not proxy_to:
                    raise ConfidentialStorageInvalidRequest(f'Vault with ID "{request.vault}" dow bot exists')
                vault: EncryptedDataVault = proxy_to[0]
                await vault.open()
                self.__sessions[request.thread.thid] = vault
                await self.__send_response(request, DataVaultOperationAck())
            elif isinstance(request, DataVaultClose):
                # Request to close
                vault = self.__sessions.get(request.thread.thid, None)
                if vault is not None:
                    await vault.close()
                    del self.__sessions[request.thread.thid]
                await self.__send_response(request, DataVaultOperationAck())
            if isinstance(request, DataVaultCreateStream):
                vault = self.__get_vault(request.thread.thid)
                if not request.uri:
                    raise ConfidentialStorageInvalidRequest('You should set "uri" attribute')
                attributes = request.attributes or {}
                structured_document = await vault.create_stream(
                    uri=request.uri, meta=request.meta, chunk_size=request.chunk_size, **attributes
                )
                response = StructuredDocumentMessage(
                    documents=[
                        StructuredDocumentAttach.create_from(src=structured_document, sequence=0)
                    ]
                )
                await self.__send_response(request, response)
            elif isinstance(request, DataVaultCreateDocument):
                vault = self.__get_vault(request.thread.thid)
                if not request.uri:
                    raise ConfidentialStorageInvalidRequest('You should set "uri" attribute')
                attributes = request.attributes or {}
                structured_document = await vault.create_document(
                    uri=request.uri, meta=request.meta, **attributes
                )
                response = StructuredDocumentMessage(
                    documents=[
                        StructuredDocumentAttach.create_from(src=structured_document, sequence=0)
                    ]
                )
                await self.__send_response(request, response)
            elif isinstance(request, DataVaultUpdateResource):
                vault = self.__get_vault(request.thread.thid)
                if not request.uri:
                    raise ConfidentialStorageInvalidRequest('You should set "uri" attribute')
                attributes = request.attributes or {}
                await vault.update(
                    uri=request.uri, meta=request.meta, **attributes
                )
                await self.__send_response(request, DataVaultOperationAck())
            elif isinstance(request, DataVaultLoadResource):
                vault = self.__get_vault(request.thread.thid)
                if not request.uri:
                    raise ConfidentialStorageInvalidRequest('You should set "uri" attribute')
                structured_document = await vault.load(request.uri)
                response = StructuredDocumentMessage(
                    documents=[
                        StructuredDocumentAttach.create_from(src=structured_document, sequence=0)
                    ]
                )
                await self.__send_response(request, response)
            elif isinstance(request, DataVaultSaveDocument):
                vault = self.__get_vault(request.thread.thid)
                if not request.uri:
                    raise ConfidentialStorageInvalidRequest('You should set "uri" attribute')
                if not request.document:
                    raise ConfidentialStorageInvalidRequest('You should attach document with "doc~attach"')
                enc_doc: EncryptedDocument = request.document.document
                await vault.save_document(uri=request.uri, doc=enc_doc)
                await self.__send_response(request, DataVaultOperationAck())

    def __get_vault(self, thid: str) -> EncryptedDataVault:
        vault = self.__sessions.get(thid, None)
        if vault is None:
            raise ConfidentialStorageInvalidRequest(f'Not found vault bind for session thread: {thid}')
        return vault

    async def __send_response(
            self,
            request_: BaseConfidentialStorageMessage,
            response_: Union[BaseConfidentialStorageMessage, DataVaultOperationAck]
    ):
        sirius_sdk.prepare_response(request_, response_)
        await sirius_sdk.send_to(response_, self.caller)
