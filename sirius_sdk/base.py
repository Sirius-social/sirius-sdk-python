import asyncio
from abc import ABC, abstractmethod
from typing import Any, Union
from urllib.parse import urljoin

import aiohttp

from sirius_sdk.messaging import Message
from sirius_sdk.errors.exceptions import *


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

    DEF_TIMEOUT = 30.0
    ENC = 'utf-8'

    def __init__(
            self, server_address: str, path: str, credentials: bytes,
            timeout: float=DEF_TIMEOUT, loop: asyncio.AbstractEventLoop=None
    ):
        self.__session = aiohttp.ClientSession(
            loop=loop,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={
                'origin': server_address,
                'credentials': credentials.decode('ascii')
            }
        )
        self._url = urljoin(server_address, path)
        self._ws = None

    def __del__(self):
        asyncio.ensure_future(self.__session.close())

    @property
    def is_open(self):
        return self._ws is not None and not self._ws.closed

    async def open(self):
        if not self.is_open:
            self._ws = await self.__session.ws_connect(url=self._url)

    async def close(self):
        if self.is_open:
            await self._ws.close()
            self._ws = None

    async def reopen(self):
        await self.close()
        await self.open()

    async def read(self, timeout: int=None) -> bytes:
        try:
            msg = await self._ws.receive(timeout=timeout)
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
        if isinstance(message, Message):
            payload = message.serialize().encode(self.ENC)
        else:
            payload = message
        await self._ws.send_bytes(payload)
        return True
