import base64
import logging
import uuid
import contextlib

from sirius_sdk.encryption.ed25519 import ensure_is_bytes
from sirius_sdk.base import AbstractStateMachine, PersistentMixin
from sirius_sdk.abstract.p2p import Pairwise
from sirius_sdk.hub.coprotocols import CoProtocolThreadedP2P
from sirius_sdk.errors.exceptions import StateMachineAborted, OperationAbortedManually, StateMachineTerminatedWithError

from .components import EncryptedDataVault, DataVaultStreamWrapper
from .messages import *
from .streams import AbstractReadOnlyStream, AbstractWriteOnlyStream, BaseStreamEncryption, StreamEncryption, \
    StreamDecryption, ReadOnlyStreamDecodingWrapper, WriteOnlyStreamEncodingWrapper
from . import ConfidentialStorageEncType, EncryptedDocument, StructuredDocument, DocumentMeta, StreamMeta
from .errors import *
from .encoding import JWE, KeyPair
from .utils import *


def problem_report_from_exception(e: BaseConfidentialStorageError) -> ConfidentialStorageMessageProblemReport:
    problem_code, explain = e.PROBLEM_CODE, e.message
    report = ConfidentialStorageMessageProblemReport(
        problem_code=problem_code, explain=explain
    )
    return report


def exception_from_problem_report(
        report: ConfidentialStorageMessageProblemReport
) -> Optional[Union[BaseConfidentialStorageError, StateMachineTerminatedWithError]]:
    if report.problem_code == ConfidentialStorageUnexpectedMessageType.PROBLEM_CODE:
        return ConfidentialStorageUnexpectedMessageType(report.explain)
    elif report.problem_code == ConfidentialStorageInvalidRequest.PROBLEM_CODE:
        return ConfidentialStorageInvalidRequest(report.explain)
    elif report.problem_code == StreamEOF.PROBLEM_CODE:
        return StreamEOF(report.explain)
    elif report.problem_code == EncryptionError.PROBLEM_CODE:
        return EncryptionError(report.explain)
    elif report.problem_code == StreamInitializationError.PROBLEM_CODE:
        return StreamInitializationError(report.explain)
    elif report.problem_code == StreamSeekableError.PROBLEM_CODE:
        return StreamSeekableError(report.explain)
    elif report.problem_code == StreamFormatError.PROBLEM_CODE:
        return StreamFormatError(report.explain)
    elif report.problem_code == DocumentFormatError.PROBLEM_CODE:
        return DocumentFormatError(report.explain)
    elif report.problem_code == ConfidentialStorageTimeoutOccurred.PROBLEM_CODE:
        return ConfidentialStorageTimeoutOccurred(report.explain)
    elif report.problem_code == ConfidentialStoragePermissionDenied.PROBLEM_CODE:
        return ConfidentialStoragePermissionDenied(report.explain)
    elif report.problem_code == DataVaultCreateResourceError.PROBLEM_CODE:
        return DataVaultCreateResourceError(report.explain)
    elif report.problem_code == DataVaultResourceMissing.PROBLEM_CODE:
        return DataVaultResourceMissing(report.explain)
    elif report.problem_code == DataVaultSessionError.PROBLEM_CODE:
        return DataVaultSessionError(report.explain)
    elif report.problem_code == DataVaultStateError.PROBLEM_CODE:
        return DataVaultStateError(report.explain)
    elif report.problem_code == DataVaultOSError.PROBLEM_CODE:
        return DataVaultOSError(report.explain)
    else:
        return BaseConfidentialStorageError(report.explain)


class CallerReadOnlyStreamProtocol(AbstractStateMachine, AbstractReadOnlyStream):
    """ReadOnly Stream protocol for Caller entity

    See details:
        - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols
    """

    def __init__(
            self, called: Pairwise, uri: str, read_timeout: int, retry_count: int = 1,
            thid: str = None, pthid: str = None, enc: BaseStreamEncryption = None, logger=None, *args, **kwargs
    ):
        """Stream abstraction for read-only operations provided with [Vault] entity

        :param called (required): Called entity who must process requests (Vault/Storage/etc)
        :param uri (required): address of stream resource
        :param read_timeout (required): time till operation is timeout occurred
        :param thid (optional): co-protocol thread-id
        :param pthid (optional): co-protocol parent-thread-id
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
        self.__pthid = pthid
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None

    @property
    def called(self) -> Pairwise:
        return self.__called

    @property
    def thid(self) -> str:
        return self.__thid

    @property
    def pthid(self) -> Optional[str]:
        return self.__pthid

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

    async def open_coprotocol(self) -> CoProtocolThreadedP2P:
        if self.__coprotocol is None:
            self.__coprotocol = CoProtocolThreadedP2P(
                thid=self.thid,
                pthid=self.pthid,
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
                        raise exc
                    else:
                        # Co-Protocol will terminate if timeout occurred
                        pass
                else:
                    err_message = 'Caller read operation timeout occurred!'
                    report = ConfidentialStorageMessageProblemReport(
                        problem_code=ConfidentialStorageTimeoutOccurred.PROBLEM_CODE,
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


class CalledReadOnlyStreamProtocol(PersistentMixin, AbstractStateMachine):
    """ReadOnly Stream protocol for Called entity, Called entity most probably operate on Vault side
       Acts as proxy to physical stream implementation

    See details:
        - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols
    """

    def __init__(
            self, caller: Pairwise, thid: str = None, proxy_to: AbstractReadOnlyStream = None,
            persistent_id: str = None, time_to_live: int = None, logger=None, *args, **kwargs
    ):
        """Setup stream proxy environment

        :param caller: Caller of stream resource operations
        :param thid (optional): co-protocol thread-id
        :param proxy_to (optional): stream to proxy op calls
        :param persistent_id (optional): unique ID to store state to recover states on failures and restarts
        :param time_to_live (optional): time the state-machine is alive,
        :param logger (optional): state-machine logger
        """
        super(CalledReadOnlyStreamProtocol, self).__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self.__caller: Pairwise = caller
        self.__thid = thid
        self.__proxy_to = proxy_to
        self.__persistent_id = persistent_id
        self.__persist_state = {}
        self.__storage_rec_exists = False
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None

    @property
    def caller(self) -> Pairwise:
        return self.__caller

    @property
    def thid(self) -> str:
        return self.__thid

    @property
    def proxy_to(self) -> Optional[AbstractReadOnlyStream]:
        return self.__proxy_to

    @property
    def stream_is_open(self) -> bool:
        return self.__persist_state.get('is_open', False)

    @stream_is_open.setter
    def stream_is_open(self, value: bool):
        self.__persist_state['is_open'] = value

    async def run_forever(self, proxy_to: AbstractReadOnlyStream = None, exit_on_close: bool = True):
        """Proxy requests in loop

        :param proxy_to: stream interface implementation
        :param exit_on_close: (bool) exit loop on close
        :return:
        """
        if proxy_to is None:
            proxy_to = self.__proxy_to
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
            proxy_to: AbstractReadOnlyStream = None
    ):
        if proxy_to is None:
            proxy_to = self.__proxy_to
        if isinstance(request, ConfidentialStorageMessageProblemReport):
            self._problem_report = request
        elif isinstance(request, StreamOperation):
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
                    await self.__send_response(request, StreamOperationResult(request.operation, params))
                    self.stream_is_open = True
                elif request.operation == StreamOperation.OperationCode.CLOSE:
                    await proxy_to.close()
                    await self.__ensure_storage_record_missing()
                elif request.operation == StreamOperation.OperationCode.SEEK_TO_CHUNK:
                    no = request.params.get('no')
                    new_no = await proxy_to.seek_to_chunk(no)
                    params = {'no': new_no}
                    await self.__send_response(request, StreamOperationResult(request.operation, params))
                elif request.operation == StreamOperation.OperationCode.READ_CHUNK:
                    no = request.params.get('no')
                    new_no, chunk = await proxy_to.read_chunk(no)
                    chunk = base64.b64encode(chunk).decode()
                    params = {'no': new_no, 'chunk': chunk}
                    await self.__send_response(request, StreamOperationResult(request.operation, params))
            except BaseConfidentialStorageError as e:
                report = problem_report_from_exception(e)
                # Don't raise any error: give caller to make decision
                await self.__send_response(request, report)
                await self.__ensure_storage_record_missing()

    async def open_coprotocol(self) -> CoProtocolThreadedP2P:
        if self.__coprotocol is None:
            self.__coprotocol = CoProtocolThreadedP2P(
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
        await self.__ensure_storage_record_missing()

    async def abort(self):
        await self.__ensure_storage_record_missing()
        await super().abort()

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

    #############################
    # Persistent methods
    #############################
    async def load(self):
        if self.__proxy_to is not None and self.__persistent_id is not None:
            new_states = await self.__ensure_storage_record_exists()
            if new_states and new_states != self.__persist_state:
                self.__persist_state = new_states
                if self.__persist_state['is_open'] is False and self.__proxy_to.is_open is True:
                    await self.__proxy_to.close()
                if self.__persist_state['is_open'] is True and self.__proxy_to.is_open is False:
                    await self.__proxy_to.open()
                if self.__proxy_to.is_open and self.__persist_state['current_chunk'] != self.__proxy_to.current_chunk:
                    await self.__proxy_to.seek_to_chunk(self.__persist_state['current_chunk'])

    async def save(self):
        if self.__proxy_to is not None and self.__persistent_id is not None:
            self.__persist_state = {'is_open': self.__proxy_to.is_open, 'current_chunk': self.__proxy_to.current_chunk}
            await update_persist_record(self.__persistent_id, self.__persist_state)

    @property
    def edited(self) -> bool:
        if self.__proxy_to is not None:
            return self.__persist_state.get('is_open', None) != self.__proxy_to.is_open or \
                   self.__persist_state.get('current_chunk', None) != self.__proxy_to.current_chunk
        else:
            return False

    async def __send_response(
            self,
            request_: StreamOperation,
            response_: Union[StreamOperationResult, ConfidentialStorageMessageProblemReport]
    ):
        sirius_sdk.prepare_response(request_, response_)
        await sirius_sdk.send_to(response_, self.caller)

    async def __ensure_storage_record_exists(self) -> Optional[dict]:
        if self.__persistent_id is not None:
            states = await ensure_persist_record_exists(self.__persistent_id, self.__persist_state)
            self.__storage_rec_exists = True
            return states
        else:
            return None

    async def __ensure_storage_record_missing(self):
        if self.__storage_rec_exists:
            await ensure_persist_record_missing(self.__persistent_id)
            self.__storage_rec_exists = False


class CallerWriteOnlyStreamProtocol(AbstractStateMachine, AbstractWriteOnlyStream):
    """WriteOnly Stream protocol for Caller entity

    See details:
        - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols
    """

    def __init__(
            self, called: Pairwise, uri: str, thid: str = None, pthid: str = None, enc: BaseStreamEncryption = None,
            retry_count: int = 3, time_to_live: int = 60, logger=None, *args, **kwargs
    ):
        """Stream abstraction for write-only operations provided with [Vault] entity

        :param called (required): Called entity who must process requests (Vault/Storage/etc)
        :param uri (required): address of stream resource
        :param thid (optional): co-protocol thread-id
        :param pthid (optional): co-protocol parent-thread-id
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
        self.__pthid = pthid
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None

    @property
    def called(self) -> Pairwise:
        return self.__called

    @property
    def thid(self) -> str:
        return self.__thid

    @property
    def pthid(self) -> Optional[str]:
        return self.__pthid

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

    async def open_coprotocol(self) -> CoProtocolThreadedP2P:
        if self.__coprotocol is None:
            self.__coprotocol = CoProtocolThreadedP2P(
                thid=self.thid,
                pthid=self.pthid,
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
                        exc = exception_from_problem_report(resp)
                        raise exc
                    else:
                        # Co-Protocol will terminate if timeout occurred
                        pass
                else:
                    err_message = 'Caller write operation timeout occurred!'
                    report = ConfidentialStorageMessageProblemReport(
                        problem_code=ConfidentialStorageTimeoutOccurred.PROBLEM_CODE,
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


class CalledWriteOnlyStreamProtocol(PersistentMixin, AbstractStateMachine):
    """
        Called entity on WriteOnly Stream side, Called entity most probably operate on Vault side
        Acts as proxy to physical stream implementation

    See details:
        - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols
    """

    def __init__(
            self, caller: Pairwise, thid: str = None, time_to_live: int = None,
            proxy_to: AbstractWriteOnlyStream = None, persistent_id: str = None,
            logger=None, *args, **kwargs
    ):
        """Setup stream proxy environment

        :param caller: Caller of stream resource operations
        :param thid (optional): co-protocol thread-id
        :param time_to_live (optional): time the state-machine is alive,
        :param proxy_to(optional): stream to proxy operations
        :param persistent_id (optional): unique ID to store state to recover states on failures and restarts
        :param logger (optional): state-machine logger
        """
        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self.__caller: Pairwise = caller
        self.__thid = thid
        self.__proxy_to = proxy_to
        self.__persistent_id = persistent_id
        self.__storage_rec_exists = False
        self.__persist_state = {}
        self.__coprotocol: Optional[CoProtocolThreadedP2P] = None
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None

    @property
    def caller(self) -> Pairwise:
        return self.__caller

    @property
    def thid(self) -> str:
        return self.__thid

    @property
    def proxy_to(self) -> Optional[AbstractWriteOnlyStream]:
        return self.__proxy_to

    @property
    def stream_is_open(self) -> bool:
        return self.__persist_state.get('is_open', False)

    @stream_is_open.setter
    def stream_is_open(self, value: bool):
        self.__persist_state['is_open'] = value

    async def run_forever(self, proxy_to: AbstractWriteOnlyStream = None, exit_on_close: bool = True):
        """Proxy requests in loop

        :param proxy_to: stream interface implementation
        :param exit_on_close: (bool) exit loop on close
        :return:
        """
        if proxy_to is None:
            proxy_to = self.__proxy_to
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
            proxy_to: AbstractWriteOnlyStream = None
    ):
        if proxy_to is None:
            proxy_to = self.__proxy_to
        if isinstance(request, ConfidentialStorageMessageProblemReport):
            self._problem_report = request
        elif isinstance(request, StreamOperation):
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
                    await self.__send_response(request, StreamOperationResult(request.operation, params))
                    self.stream_is_open = True
                elif request.operation == StreamOperation.OperationCode.CLOSE:
                    await proxy_to.close()
                    await self.__ensure_storage_record_missing()
                elif request.operation == StreamOperation.OperationCode.SEEK_TO_CHUNK:
                    no = request.params.get('no')
                    new_no = await proxy_to.seek_to_chunk(no)
                    params = {'no': new_no}
                    await self.__send_response(request, StreamOperationResult(request.operation, params))
                elif request.operation == StreamOperation.OperationCode.WRITE_CHUNK:
                    no = request.params.get('no')
                    chunk = base64.b64decode(request.params.get('chunk'))
                    new_no, writen_sz = await proxy_to.write_chunk(chunk, no)
                    params = {'no': new_no, 'size': writen_sz}
                    await self.__send_response(request, StreamOperationResult(request.operation, params))
                elif request.operation == StreamOperation.OperationCode.TRUNCATE:
                    no = request.params.get('no')
                    await proxy_to.truncate(no)
                    params = {
                        'state': {
                            'chunks_num': proxy_to.chunks_num,
                            'current_chunk': proxy_to.current_chunk
                        }
                    }
                    await self.__send_response(request, StreamOperationResult(request.operation, params))
            except BaseConfidentialStorageError as e:
                report = problem_report_from_exception(e)
                # Don't raise any error: give caller to make decision
                await self.__send_response(request, report)
                await self.__ensure_storage_record_missing()

    async def open_coprotocol(self) -> CoProtocolThreadedP2P:
        if self.__coprotocol is None:
            self.__coprotocol = CoProtocolThreadedP2P(
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
        if self.__persistent_id:
            await self.__ensure_storage_record_missing()

    async def abort(self):
        await self.__ensure_storage_record_missing()
        await super().abort()

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

    #############################
    # Persistent methods
    #############################
    async def load(self):
        if self.__proxy_to is not None and self.__persistent_id is not None:
            new_states = await self.__ensure_storage_record_exists()
            if new_states and new_states != self.__persist_state:
                self.__persist_state = new_states
                if self.__persist_state['is_open'] is False and self.__proxy_to.is_open is True:
                    await self.__proxy_to.close()
                if self.__persist_state['is_open'] is True and self.__proxy_to.is_open is False:
                    await self.__proxy_to.open()
                if self.__proxy_to.is_open and self.__persist_state['current_chunk'] != self.__proxy_to.current_chunk:
                    await self.__proxy_to.seek_to_chunk(self.__persist_state['current_chunk'])

    async def save(self):
        if self.__proxy_to is not None and self.__persistent_id is not None:
            self.__persist_state = {'is_open': self.__proxy_to.is_open, 'current_chunk': self.__proxy_to.current_chunk}
            await update_persist_record(self.__persistent_id, self.__persist_state)

    @property
    def edited(self) -> bool:
        if self.__proxy_to is not None:
            return self.__persist_state.get('is_open', None) != self.__proxy_to.is_open or \
                   self.__persist_state.get('current_chunk', None) != self.__proxy_to.current_chunk
        else:
            return False

    async def __send_response(
            self,
            request_: StreamOperation,
            response_: Union[StreamOperationResult, ConfidentialStorageMessageProblemReport]
    ):
        sirius_sdk.prepare_response(request_, response_)
        await sirius_sdk.send_to(response_, self.caller)

    async def __ensure_storage_record_exists(self) -> Optional[dict]:
        if self.__persistent_id is not None:
            states = await ensure_persist_record_exists(self.__persistent_id, self.__persist_state)
            self.__storage_rec_exists = True
            return states
        else:
            return None

    async def __ensure_storage_record_missing(self):
        if self.__storage_rec_exists:
            await ensure_persist_record_missing(self.__persistent_id)
            self.__storage_rec_exists = False


class CallerEncryptedDataVault(AbstractStateMachine, EncryptedDataVault, EncryptedDataVault.Indexes):

    class CallerStreamWrapper(DataVaultStreamWrapper):

        def __init__(self, api: EncryptedDataVault, id_: str):
            self.__api = api
            self.__id = id_
            super().__init__(readable=None, writable=None)

        async def readable(self, jwe: Union[JWE, dict] = None, keys: KeyPair = None) -> AbstractReadOnlyStream:
            if self._readable is None:
                self._readable = await self.__api.readable(self.__id)
            if jwe is None:
                return self._readable
            else:
                enc = StreamDecryption.from_jwe(jwe)
                if keys is not None:
                    enc.setup(vk=keys.pk, sk=keys.sk)
                return ReadOnlyStreamDecodingWrapper(src=self._readable, enc=enc)

        async def writable(self, jwe: Union[JWE, dict] = None, cek: Union[bytes, str] = None) -> AbstractWriteOnlyStream:
            if self._writable is None:
                self._writable = await self.__api.writable(self.__id)
            if jwe is None:
                return self._writable
            else:
                if isinstance(cek, str):
                    cek = ensure_is_bytes(cek)
                return WriteOnlyStreamEncodingWrapper(dest=self._writable, enc=StreamEncryption.from_jwe(jwe, cek))

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
        self.__read_timeout = read_timeout
        self.__retry_count = retry_count

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
        await self._rpc(request=DataVaultClose())
        await self._close_coprotocol()

    async def list_vaults(self) -> List[VaultConfig]:
        resp = await self._request(request=DataVaultQueryList())
        if isinstance(resp, DataVaultResponseList):
            return resp.vaults
        elif isinstance(resp, ConfidentialStorageMessageProblemReport):
            exc = exception_from_problem_report(resp)
            raise exc
        else:
            raise RuntimeError(f'Unexpected response type: {resp.__class__.__name__}')

    async def filter(self, **attributes) -> List[StructuredDocument]:
        resp = await self._rpc(
            request=DataVaultList(
                filters=dict(**attributes) if attributes else None
            )
        )
        if isinstance(resp, StructuredDocumentMessage):
            docs = []
            for attach in resp.documents:
                doc = self.__extract_structured_doc(attach)
                docs.append(doc)
            return docs
        else:
            raise ConfidentialStorageUnexpectedMessageType(resp)

    async def indexes(self) -> EncryptedDataVault.Indexes:
        return self

    async def create_stream(self, uri: str, meta: Union[dict, StreamMeta] = None, chunk_size: int = None, **attributes) -> StructuredDocument:
        resp = await self._rpc(
            request=DataVaultCreateStream(uri=uri, meta=meta, chunk_size=chunk_size, attributes=attributes)
        )
        if isinstance(resp, StructuredDocumentMessage):
            attach = resp.documents[0]
            doc = self.__extract_structured_doc(attach)
            return doc
        else:
            raise ConfidentialStorageUnexpectedMessageType(resp)

    async def create_document(self, uri: str, meta: Union[dict, DocumentMeta] = None, **attributes) -> StructuredDocument:
        resp = await self._rpc(
            request=DataVaultCreateDocument(uri=uri, meta=meta, attributes=attributes)
        )
        if isinstance(resp, StructuredDocumentMessage):
            attach = resp.documents[0]
            doc = self.__extract_structured_doc(attach)
            if doc.doc is None:
                doc.doc = EncryptedDocument(content=b'')
            return doc
        else:
            raise ConfidentialStorageUnexpectedMessageType(resp)

    async def remove(self, uri: str):
        await self._rpc(
            request=DataVaultRemoveResource(uri=uri)
        )

    async def update(self, uri: str, meta: Union[dict, StreamMeta, DocumentMeta] = None, **attributes):
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
        request = DataVaultSaveDocument(uri=uri)
        request.document = doc
        await self._rpc(request)

    async def readable(self, uri: str) -> AbstractReadOnlyStream:
        stream = CallerReadOnlyStreamProtocol(
            called=self.called, uri=uri, pthid=self.thid,
            read_timeout=self.__read_timeout,
            retry_count=self.__retry_count,
        )
        await self._rpc(
            request=DataVaultBindStreamForReading(uri=uri, co_binding_id=stream.thid)
        )
        return stream

    async def writable(self, uri: str) -> AbstractWriteOnlyStream:
        stream = CallerWriteOnlyStreamProtocol(
            called=self.called, uri=uri, pthid=self.thid,
            retry_count=self.__retry_count,
            time_to_live=60*60  # 1 hour
        )
        await self._rpc(
            request=DataVaultBindStreamForWriting(uri=uri, co_binding_id=stream.thid)
        )
        return stream

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
                    problem_code=ConfidentialStorageTimeoutOccurred.PROBLEM_CODE,
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
                        exc = exception_from_problem_report(resp)
                        raise exc
                    else:
                        raise ConfidentialStorageUnexpectedMessageType(resp)
                else:
                    err_message = 'Caller write operation timeout occurred!'
                    raise ConfidentialStorageTimeoutOccurred(err_message)

    async def _open_coprotocol(self) -> CoProtocolThreadedP2P:
        if self.__coprotocol is None:
            self.__coprotocol = CoProtocolThreadedP2P(
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

    def __extract_structured_doc(self, attach: StructuredDocumentAttach) -> StructuredDocument:
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
            ],
            content=attach.document,
        )
        if attach.stream is not None:
            doc.stream = self.CallerStreamWrapper(api=self, id_=attach.stream.id)
        return doc


class CalledEncryptedDataVault(AbstractStateMachine):

    STREAM_CATEGORY_READER = 'reader'
    STREAM_CATEGORY_WRITER = 'writer'

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
        self.__read_sessions: Dict[str, Dict[str, CalledReadOnlyStreamProtocol]] = {}
        self.__write_sessions: Dict[str, Dict[str, CalledWriteOnlyStreamProtocol]] = {}
        self._problem_report: Optional[ConfidentialStorageMessageProblemReport] = None

    @property
    def caller(self) -> Pairwise:
        return self.__caller

    @property
    def proxy_to(self) -> List[EncryptedDataVault]:
        return self.__proxy_to

    async def handle(self, request: BaseConfidentialStorageMessage):
        try:
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
                        read_sessions = self.__read_sessions.get(request.thread.thid, {})
                        for thid, proto in read_sessions.items():
                            await proto.proxy_to.close()
                            await proto.close_coprotocol()
                            # Clean storage
                            persist_id_uri, _ = self.__build_persist_ids(
                                thid=request.thread.thid, co_binding_id=thid, category=self.STREAM_CATEGORY_READER
                            )
                            await ensure_persist_record_missing(persist_id_uri)
                        if read_sessions:
                            del self.__read_sessions[request.thread.thid]
                        write_sessions = self.__write_sessions.get(request.thread.thid, {})
                        for thid, proto in write_sessions.items():
                            await proto.proxy_to.close()
                            await proto.close_coprotocol()
                            # Clean storage
                            persist_id_uri, _ = self.__build_persist_ids(
                                thid=request.thread.thid, co_binding_id=thid, category=self.STREAM_CATEGORY_WRITER
                            )
                            await ensure_persist_record_missing(persist_id_uri)
                        if write_sessions:
                            del self.__write_sessions[request.thread.thid]
                        await vault.close()
                        del self.__sessions[request.thread.thid]
                    await self.__send_response(request, DataVaultOperationAck())
                elif isinstance(request, DataVaultCreateStream):
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
                elif isinstance(request, DataVaultRemoveResource):
                    vault = self.__get_vault(request.thread.thid)
                    if not request.uri:
                        raise ConfidentialStorageInvalidRequest('You should set "uri" attribute')
                    await vault.remove(request.uri)
                    await self.__send_response(request, DataVaultOperationAck())
                elif isinstance(request, DataVaultSaveDocument):
                    vault = self.__get_vault(request.thread.thid)
                    if not request.uri:
                        raise ConfidentialStorageInvalidRequest('You should set "uri" attribute')
                    if not request.document:
                        raise ConfidentialStorageInvalidRequest('You should attach document with "doc~attach"')
                    await vault.save_document(uri=request.uri, doc=request.document)
                    await self.__send_response(request, DataVaultOperationAck())
                elif isinstance(request, DataVaultList):
                    vault = self.__get_vault(request.thread.thid)
                    attributes = request.filters
                    indexes = await vault.indexes()
                    structured_documents = await indexes.filter(**attributes)
                    response = StructuredDocumentMessage(
                        documents=[
                            StructuredDocumentAttach.create_from(src=doc, sequence=i)
                            for i, doc in enumerate(structured_documents)
                        ]
                    )
                    await self.__send_response(request, response)
                elif isinstance(request, DataVaultBindStreamForWriting) or isinstance(request, DataVaultBindStreamForReading):
                    vault = self.__get_vault(request.thread.thid)
                    if not request.uri:
                        raise ConfidentialStorageInvalidRequest('You should set "uri" attribute')
                    if not request.co_binding_id:
                        raise ConfidentialStorageInvalidRequest('You should set "co_binding_id" attribute to bind thread')
                    if isinstance(request, DataVaultBindStreamForWriting):
                        category = self.STREAM_CATEGORY_WRITER
                        # stream = await vault.writable(uri=request.uri)
                        # proto = CalledWriteOnlyStreamProtocol(
                        #     caller=self.caller, thid=request.co_binding_id, proxy_to=stream
                        # )
                        # write_sessions = self.__write_sessions.get(thread.thid, {})
                        # write_sessions[request.co_binding_id] = proto
                        # self.__write_sessions[thread.thid] = write_sessions
                    else:
                        category = self.STREAM_CATEGORY_READER
                        # stream = await vault.readable(uri=request.uri)
                        # proto = CalledReadOnlyStreamProtocol(
                        #     caller=self.caller, thid=request.co_binding_id, proxy_to=stream
                        # )
                        # read_sessions = self.__read_sessions.get(thread.thid, {})
                        # read_sessions[request.co_binding_id] = proto
                        # self.__read_sessions[thread.thid] = read_sessions
                    persist_id_uri, _ = self.__build_persist_ids(
                        thid=request.thread.thid, co_binding_id=request.co_binding_id, category=category
                    )
                    await store_persist_record_value(persist_id_uri, request.uri)
                    await self.__send_response(request, DataVaultOperationAck())
                else:
                    raise ConfidentialStorageUnexpectedMessageType(request)
            elif isinstance(request, StreamOperation):
                # Process Stream operation
                thread = request.thread
                if thread is None or not thread.thid:
                    raise ConfidentialStorageInvalidRequest(
                        'Stream operation request should have "~thread.thid" attribute to bind sessions'
                    )
                if thread.pthid is None:
                    raise ConfidentialStorageInvalidRequest(
                        'Stream operation request should have "~thread.pthid" attribute to bind sessions'
                    )
                proto = await self.__load_stream(request.thread)
                if proto is not None:
                    await proto.handle(request)
                    if proto.edited:
                        await proto.save()
                # proto = self.__write_sessions.get(thread.pthid, {}).get(thread.thid, None)
                # if proto is not None:
                #     await proto.handle(request)
                # proto = self.__read_sessions.get(thread.pthid, {}).get(thread.thid, None)
                # if proto is not None:
                #     await proto.handle(request)
            else:
                raise ConfidentialStorageUnexpectedMessageType(request)
        except BaseConfidentialStorageError as e:
            report = problem_report_from_exception(e)
            # Don't raise any error: give caller to make decision
            await self.__send_response(request, report)
        except OSError as e:
            exc = DataVaultOSError(e)
            report = problem_report_from_exception(exc)
            await self.__send_response(request, report)

    def __get_vault(self, thid: str) -> EncryptedDataVault:
        vault = self.__sessions.get(thid, None)
        if vault is None:
            raise ConfidentialStorageInvalidRequest(f'Not found vault bind for session thread: {thid}')
        return vault

    async def __load_stream(
            self, thread: BaseDataVaultOperation.Thread,
    ) -> Optional[Union[CalledWriteOnlyStreamProtocol, CalledReadOnlyStreamProtocol]]:
        reading_proto = self.__read_sessions.get(thread.pthid, {}).get(thread.thid, None)
        if reading_proto is not None:
            return reading_proto
        writing_proto = self.__write_sessions.get(thread.pthid, {}).get(thread.thid, None)
        if writing_proto is not None:
            return writing_proto
        # If no one is found then try to load states
        vault = self.__get_vault(thread.pthid)
        for category in [self.STREAM_CATEGORY_READER, self.STREAM_CATEGORY_WRITER]:
            persist_id_uri, persist_id_proto = self.__build_persist_ids(
                thid=thread.pthid, co_binding_id=thread.thid, category=category
            )
            uri = await load_persist_record_value(persist_id_uri)
            if uri is not None:
                # Restore states
                if category == self.STREAM_CATEGORY_WRITER:
                    stream = await vault.writable(uri)
                    proto = CalledWriteOnlyStreamProtocol(
                        caller=self.caller, thid=thread.thid, proxy_to=stream, persistent_id=persist_id_proto
                    )
                    await proto.load()
                    write_sessions = self.__write_sessions.get(thread.pthid, {})
                    write_sessions[thread.thid] = proto
                    self.__write_sessions[thread.pthid] = write_sessions
                    return proto
                elif category == self.STREAM_CATEGORY_READER:
                    stream = await vault.readable(uri)
                    proto = CalledReadOnlyStreamProtocol(
                        caller=self.caller, thid=thread.thid, proxy_to=stream, persistent_id=persist_id_proto
                    )
                    await proto.load()
                    read_sessions = self.__read_sessions.get(thread.pthid, {})
                    read_sessions[thread.thid] = proto
                    self.__read_sessions[thread.pthid] = read_sessions
                    return proto
        return None

    @staticmethod
    def __build_persist_ids(thid: str, co_binding_id: str, category: str) -> (str, str):
        common_prefix = f'{thid}/{co_binding_id}/{category}'
        persist_id_for_uri = f'{common_prefix}:uri'
        persist_id_for_proto = f'{common_prefix}:proto'
        return persist_id_for_uri, persist_id_for_proto

    async def __send_response(
            self,
            request_: BaseConfidentialStorageMessage,
            response_: Union[BaseConfidentialStorageMessage, DataVaultOperationAck, ConfidentialStorageMessageProblemReport]
    ):
        sirius_sdk.prepare_response(request_, response_)
        await sirius_sdk.send_to(response_, self.caller)
