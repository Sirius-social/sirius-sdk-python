import json
from abc import ABC, abstractmethod
from typing import Any, Union
from urllib.parse import urljoin

import aiohttp

from sirius_sdk.errors.exceptions import SiriusConnectionClosed, SiriusIOError, SiriusUnsupportedData, \
    SiriusInvalidPayloadStructure


class ReadOnlyChannel(ABC):
    """Communication abstraction for reading data stream
    """

    @abstractmethod
    async def read(self, timeout: int=None) -> Any:
        """Read message packet

        :param timeout: Operation timeout is sec
        :return: message packet
        """
        raise NotImplemented()


class WriteOnlyChannel(ABC):
    """Communication abstraction for writing data stream
    """

    @abstractmethod
    async def write(self, data: Any) -> bool:
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


class BaseWebSocketConnector(BaseConnector):

    DEF_TIMEOUT = 30.0
    ENC = 'utf-8'

    def __init__(self, server_address: str, path: str, credentials: bytes, timeout: float=DEF_TIMEOUT):
        self.__session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={
                'origin': server_address,
                'credentials': credentials.decode('ascii')
            }
        )
        self._url = urljoin(server_address, path)
        self._ws = None

    @property
    def is_open(self):
        return self._ws is not None

    async def open(self):
        if not self.is_open:
            self._ws = await self.__session.ws_connect(url=self._url)

    async def close(self):
        if not self.is_open:
            await self._ws.close()
            self._ws = None

    async def read(self, timeout: int=None) -> Any:
        msg = await self._ws.receive(timeout=timeout)
        if msg.type in [aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED]:
            raise SiriusConnectionClosed()
        elif msg.type in [aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY]:
            return self.parse(msg.data)
        elif msg.type == aiohttp.WSMsgType.ERROR:
            raise SiriusIOError

    async def write(self, data: Any):
        if isinstance(data, dict):
            payload = json.dumps(data).encode(self.ENC)
        elif isinstance(data, bytes):
            payload = data
        else:
            raise SiriusUnsupportedData()
        await self._ws.send_bytes(payload)

    @classmethod
    def parse(cls, payload: Union[str, bytes]):
        try:
            if isinstance(payload, str):
                return json.loads(payload)
            elif isinstance(payload, bytes):
                return json.loads(payload.decode(cls.ENC))
            else:
                raise SiriusInvalidPayloadStructure()
        except json.JSONDecodeError:
            raise SiriusInvalidPayloadStructure()
