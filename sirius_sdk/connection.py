import json
from typing import Any, Union
from abc import abstractmethod
from urllib.parse import urljoin

import aiohttp

from .exceptions import *
from .core import BaseConnector


class BaseWebSocketConnector(BaseConnector):

    DEF_TIMEOUT = 30.0
    ENC = 'utf-8'

    def __init__(self, address: str, credentials: bytes, timeout: float=DEF_TIMEOUT):
        self.__session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={
                'credentials': credentials.decode('ascii')
            }
        )
        self._url = urljoin(address, self.url_path())
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

    async def read(self) -> Any:
        msg = await self._ws.receive()
        if msg.type in [aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED]:
            raise ConnectionClosed()
        elif msg.type in [aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY]:
            return self.parse(msg.data)
        elif msg.type == aiohttp.WSMsgType.ERROR:
            raise ErrorIO

    async def write(self, data: Any):
        pass

    @classmethod
    def parse(cls, payload: Union[str, bytes]):
        try:
            if isinstance(payload, str):
                return json.loads(payload)
            elif isinstance(payload, bytes):
                return json.loads(payload.decode(cls.ENC))
            else:
                raise InvalidPayloadStructure()
        except json.JSONDecodeError:
            raise InvalidPayloadStructure()

    @classmethod
    @abstractmethod
    def url_path(cls) -> str:
        raise NotImplemented()


class RPCWebSocketConnector(BaseWebSocketConnector):

    def __init__(self, address: str, credentials: bytes, timeout: float = BaseWebSocketConnector.DEF_TIMEOUT):
        super().__init__(address, credentials, timeout)

    @classmethod
    def url_path(cls):
        return '/rpc'
