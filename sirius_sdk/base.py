import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Union, List, Optional
from urllib.parse import urljoin
from inspect import iscoroutinefunction

import aiohttp

from sirius_sdk.messaging import Message
from sirius_sdk.errors.exceptions import *


INFINITE_TIMEOUT = -1


class JsonSerializable:

    @abstractmethod
    def serialize(self) -> dict:
        raise NotImplemented

    @classmethod
    @abstractmethod
    def deserialize(cls, buffer: Union[dict, bytes, str]):
        raise NotImplemented


class ReadOnlyChannel(ABC):
    """Communication abstraction for reading data stream
    """

    @abstractmethod
    async def read(self, timeout: int=None) -> bytes:
        """Read message packet

        :param timeout: Operation timeout is sec
        :return: chunk of data stream
        """
        raise NotImplemented()


class WriteOnlyChannel(ABC):
    """Communication abstraction for writing data stream
    """

    @abstractmethod
    async def write(self, data: bytes) -> bool:
        """
        Write message packet

        :param data: message packet
        :return: True if success ele False
        """
        raise NotImplemented()


class BaseConnector(ReadOnlyChannel, WriteOnlyChannel):
    """Transport Layer.

    Connectors operate as transport provider for high-level abstractions
    """

    @abstractmethod
    async def open(self):
        """Open communication
        """
        raise NotImplemented()

    @abstractmethod
    async def close(self):
        """Close communication
        """
        raise NotImplemented()


class WebSocketConnector(BaseConnector):

    DEF_TIMEOUT = 60.0
    ENC = 'utf-8'

    def __init__(
            self, server_address: str, path: str, credentials: bytes,
            timeout: float = DEF_TIMEOUT, loop: asyncio.AbstractEventLoop = None,
            extra: dict = None
    ):
        headers = {
            'origin': server_address,
            'credentials': credentials.decode('ascii')
        }
        if extra:
            headers['extra'] = json.dumps(extra)
        self.__session = aiohttp.ClientSession(
            loop=loop,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers=headers
        )
        self._url = urljoin(server_address, path)
        self._ws = None
        self.__timeout = timeout

    def __del__(self):
        asyncio.ensure_future(self.__session.close())

    @property
    def is_open(self):
        return self._ws is not None and not self._ws.closed

    async def open(self):
        if not self.is_open:
            self._ws = await self.__session.ws_connect(url=self._url, ssl=False)

    async def close(self):
        if self.is_open:
            await self._ws.close()
            self._ws = None

    async def reopen(self):
        await self.close()
        await self.open()

    async def read(self, timeout: float = None) -> bytes:
        if timeout == INFINITE_TIMEOUT:
            _timeout = None
        else:
            _timeout = timeout or self.__timeout
        try:
            msg = await self._ws.receive(timeout=_timeout)
        except asyncio.TimeoutError as e:
            raise SiriusTimeoutIO() from e
        if msg.type in [aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED]:
            raise SiriusConnectionClosed()
        elif msg.type == aiohttp.WSMsgType.TEXT:
            return msg.data.encode(self.ENC)
        elif msg.type == aiohttp.WSMsgType.BINARY:
            return msg.data
        elif msg.type == aiohttp.WSMsgType.ERROR:
            raise SiriusIOError()

    async def write(self, message: Union[Message, bytes]) -> bool:
        if self.is_open:
            if isinstance(message, Message):
                payload = message.serialize().encode(self.ENC)
            else:
                payload = message
            await self._ws.send_bytes(payload)
            return True
        else:
            return False


class AbstractStateMachine(ABC):

    def __init__(self, time_to_live: Optional[int] = 60, logger=None, *args, **kwargs):
        """
        :param time_to_live: state machine time to live to finish progress
        """
        self.__time_to_live = time_to_live
        self.__is_aborted = False
        if logger is not None:
            if iscoroutinefunction(logger) or callable(logger):
                pass
            else:
                raise RuntimeError('Expect logger is iscoroutine function or callable object')
        self.__logger = logger
        self.__coprotocols = []

    @property
    def time_to_live(self) -> Optional[int]:
        return self.__time_to_live

    @property
    def is_aborted(self) -> bool:
        return self.__is_aborted

    async def abort(self):
        """Abort state-machine"""
        self.__is_aborted = True
        for co in self.__coprotocols:
            await co.abort()
        self.__coprotocols.clear()

    async def log(self, **kwargs) -> bool:
        if self.__logger:
            kwargs = dict(**kwargs)
            kwargs['state_machine_id'] = id(self)
            await self.__logger(**kwargs)
        else:
            return False

    def _register_for_aborting(self, co):
        self.__coprotocols.append(co)

    def _unregister_for_aborting(self, co):
        self.__coprotocols = [item for item in self.__coprotocols if id(item) != id(co)]


class PersistentMixin:

    @abstractmethod
    async def load(self):
        """Load states from external persistent storage"""
        raise NotImplemented

    @abstractmethod
    async def save(self):
        """Save states to external persistent storage"""
        raise NotImplemented

    @property
    @abstractmethod
    def edited(self) -> bool:
        """Indicate instance state was changed and woult be need to save"""
        raise NotImplemented


