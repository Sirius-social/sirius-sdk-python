import datetime
from typing import List, Any
from abc import ABC, abstractmethod

from ..base import WebSocketConnector
from ..encryption import P2PConnection
from ..rpc import AddressedTunnel, build_request, Future
from ..errors.exceptions import *


class Endpoint:
    """Available Agent endpoints
    https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0094-cross-domain-messaging
    """

    def __init__(self, url: str, routing_keys: List[str]):
        self.__url = url
        self.__routing_keys = routing_keys

    @property
    def address(self):
        return self.__url

    @property
    def routing_keys(self) -> List[str]:
        return self.__routing_keys


class BaseAgentConnection(ABC):

    IO_TIMEOUT = 30

    def __init__(self, server_address: str, credentials: bytes, p2p: P2PConnection):
        self.__connector = WebSocketConnector(
            server_address=server_address,
            path=self._path(),
            credentials=credentials,
            timeout=self.IO_TIMEOUT
        )
        self.__p2p = p2p
        self.__tunnel_rpc = None
        self.__tunnel_subprotocol = None

    @classmethod
    async def create(cls, server_address: str, credentials: bytes, p2p: P2PConnection):
        instance = cls(server_address, credentials, p2p)
        await instance.__connector.open()
        context = await instance.__connector.read(timeout=cls.IO_TIMEOUT)

    async def remote_call(self, msg_type: str, **params) -> Any:
        future = Future(
            tunnel=self.__tunnel_rpc,
            expiration_time=datetime.datetime.now() + datetime.timedelta(seconds=self.IO_TIMEOUT)
        )
        request = build_request(
            msg_type=msg_type,
            future=future,
            params=params
        )
        if not await self.__tunnel_rpc.write(request):
            raise SiriusRPCError()
        success = await future.wait(timeout=self.IO_TIMEOUT)
        if success:
            if future.has_exception():
                future.raise_exception()
            else:
                return future.get_value()
        else:
            raise SiriusTimeoutRPC()

    @classmethod
    @abstractmethod
    def _path(cls):
        raise NotImplemented()


class AgentRPC(BaseAgentConnection):

    @classmethod
    def _path(cls):
        return '/rpc'


class AgentEvents(BaseAgentConnection):

    @classmethod
    def _path(cls):
        return '/events'
