import asyncio
from typing import Union

import aiohttp

from sirius_sdk.base import BaseConnector
from sirius_sdk.agent.wallet.abstract import AbstractCrypto
from sirius_sdk.errors.exceptions import *
from sirius_sdk.messaging import Message


class MediatorConnector(BaseConnector):

    IO_TIMEOUT = 60
    ENC = 'utf-8'

    def __init__(
            self, uri: str, my_verkey: str, mediator_verkey: str,
            crypto: AbstractCrypto, loop: asyncio.AbstractEventLoop = None, timeout: int = IO_TIMEOUT,
            http_headers: dict = None
    ):
        self.__session = aiohttp.ClientSession(
            loop=loop,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers=http_headers
        )
        self._uri = uri
        self._mediator_verkey = mediator_verkey
        self._my_verkey = my_verkey
        self._crypto = crypto
        self._ws = None
        self.__timeout = timeout

    def __del__(self):
        asyncio.ensure_future(self.__session.close())

    @property
    def is_open(self):
        return self._ws is not None and not self._ws.closed

    async def open(self):
        if not self.is_open:
            self._ws = await self.__session.ws_connect(url=self._uri, ssl=False)

    async def close(self):
        if self.is_open:
            await self._ws.close()
            self._ws = None

    async def read(self, timeout: int = None) -> bytes:
        try:
            msg = await self._ws.receive(timeout=timeout or self.__timeout)
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
