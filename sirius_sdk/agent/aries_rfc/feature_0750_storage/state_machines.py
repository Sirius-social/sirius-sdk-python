import uuid
import contextlib
from enum import Enum
from typing import Optional, Union, List, Dict, Any, Tuple

import sirius_sdk
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.hub import CoProtocolThreadedP2P
from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.errors.exceptions import StateMachineAborted, OperationAbortedManually, StateMachineTerminatedWithError
from sirius_sdk.errors.exceptions import SiriusTimeoutIO

from .messages import StreamOperation, StreamOperationResult, ConfidentialStorageMessageProblemReport
from .streams import AbstractReadOnlyStream


class ReadOnlyStream(AbstractStateMachine, AbstractReadOnlyStream):
    """
    """

    def __init__(
            self, vault: Pairwise, uri: str,
            thid: str = None, time_to_live: int = None, logger=None, *args, **kwargs
    ):
        """Stream abstraction for read-only operations provided with [Vault] entity

        :param vault (required): Vault
        :param thid (optional): co-protocol thread-id
        :param pthid (optional): parent co-protocol thread-id
        :param time_to_live (optional): time the state-machine is alive,
        :param logger (optional): state-machine logger
        """
        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self._problem_report = None
        self.__uri = uri
        self.__time_to_live = time_to_live
        self.__vault = vault
        self.__thid = thid or uuid.uuid4().hex
        self.__size: int = 0
        self.__position: int = 0

    async def open(self):
        resp = await self.rpc(
            request=StreamOperation(
                operation=StreamOperation.OperationCode.OPEN,
                params={
                    'uri': self.__uri
                }
            )
        )
        self.__size = await self.seek(-1)
        await self.seek(0)

    async def close(self):
        async with self.coprotocol() as co:
            req = StreamOperation(
                operation=StreamOperation.OperationCode.CLOSE
            )
            await co.send(req)

    async def seek(self, pos: int) -> int:
        return self.__position < self.__size

    async def read_chunk(self) -> bytes:
        raw = await self.rpc(
            request=StreamOperation(
                operation=StreamOperation.OperationCode.READ
            )
        )
        return b''

    async def eof(self) -> bool:
        return False

    @contextlib.asynccontextmanager
    async def coprotocol(self):
        co = sirius_sdk.CoProtocolThreadedP2P(
            thid=self.__thid,
            to=self.__vault,
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
                resp = await co.switch(request)
                if isinstance(resp, StreamOperationResult):
                    return resp
                elif isinstance(resp, ConfidentialStorageMessageProblemReport):
                    raise StateMachineTerminatedWithError(problem_code=resp.problem_code, explain=resp.explain)
                else:
                    # Co-Protocol will terminate if timeout occurred
                    pass
