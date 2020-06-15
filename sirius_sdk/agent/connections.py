import json
import hashlib
import asyncio
import datetime
from typing import List, Any
from abc import ABC, abstractmethod

from ..base import WebSocketConnector
from ..encryption import P2PConnection
from ..rpc import AddressedTunnel, build_request, Future
from ..messaging import Message
from ..errors.exceptions import *


class Endpoint:
    """Active Agent endpoints
    https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0094-cross-domain-messaging
    """

    def __init__(self, address: str, routing_keys: List[str], is_default: bool=False):
        self.__url = address
        self.__routing_keys = routing_keys
        self.__is_default = is_default

    @property
    def address(self):
        return self.__url

    @property
    def routing_keys(self) -> List[str]:
        return self.__routing_keys

    @property
    def is_default(self):
        return self.__is_default


class BaseAgentConnection(ABC):

    IO_TIMEOUT = 30
    MSG_TYPE_CONTEXT = 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/context'

    def __init__(self, server_address: str, credentials: bytes, p2p: P2PConnection):
        self._connector = WebSocketConnector(
            server_address=server_address,
            path=self._path(),
            credentials=credentials,
            timeout=self.IO_TIMEOUT
        )
        self._p2p = p2p

    @classmethod
    async def create(cls, server_address: str, credentials: bytes, p2p: P2PConnection):
        """
        :param server_address: address of the server, example: https://server.com
        :param credentials: encrypted credentials to access cloud-based services
        :param p2p: encrypted pairwise connection between smart-contract and agent
        """
        instance = cls(server_address, credentials, p2p)
        await instance._connector.open()
        payload = await instance._connector.read(timeout=cls.IO_TIMEOUT)
        context = Message.deserialize(payload.decode())
        msg_type = context.get('@type', None)
        if msg_type is None:
            raise RuntimeError('message @type is empty')
        elif msg_type != cls.MSG_TYPE_CONTEXT:
            raise RuntimeError('message @type is empty')
        else:
            await instance._setup(context)
        return instance

    @classmethod
    @abstractmethod
    def _path(cls):
        raise NotImplemented()

    async def _setup(self, context: Message):
        pass


class AgentRPC(BaseAgentConnection):
    """RPC service.

    Proactive form of Smart-Contract design
    """

    def __init__(self, server_address: str, credentials: bytes, p2p: P2PConnection):
        super().__init__(server_address, credentials, p2p)
        self.__tunnel_rpc = None
        self.__tunnel_coprotocols = None
        self.__endpoints = []

    @property
    def endpoints(self):
        return self.__endpoints

    async def remote_call(self, msg_type: str, params: dict=None) -> Any:
        future = Future(
            tunnel=self.__tunnel_rpc,
            expiration_time=datetime.datetime.now() + datetime.timedelta(seconds=self.IO_TIMEOUT)
        )
        request = build_request(
            msg_type=msg_type,
            future=future,
            params=params or {}
        )
        if not await self.__tunnel_rpc.post(request):
            raise SiriusRPCError()
        # packet = await self.__tunnel_rpc.

        success = await future.wait(timeout=self.IO_TIMEOUT)
        if success:
            if future.has_exception():
                future.raise_exception()
            else:
                return future.get_value()
        else:
            raise SiriusTimeoutRPC()

    @classmethod
    def _path(cls):
        return '/rpc'

    async def _setup(self, context: Message):
        # Extract proxy info
        proxies = context.get('~proxy', [])
        channel_rpc = None
        channel_sub_protocol = None
        for proxy in proxies:
            if proxy['id'] == 'reverse':
                channel_rpc = proxy['data']['json']['address']
            elif proxy['id'] == 'sub-protocol':
                channel_sub_protocol = proxy['data']['json']['address']
        if channel_rpc is None:
            raise RuntimeError('rpc channel is empty')
        if channel_sub_protocol is None:
            raise RuntimeError('sub-protocol channel is empty')
        self.__tunnel_rpc = AddressedTunnel(
            address=channel_rpc, input_=self._connector, output_=self._connector, p2p=self._p2p
        )
        self.__tunnel_coprotocols = AddressedTunnel(
            address=channel_sub_protocol, input_=self._connector, output_=self._connector, p2p=self._p2p
        )
        # Extract active endpoints
        endpoints = context.get('~endpoints', [])
        endpoint_collection = []
        for endpoint in endpoints:
            body = endpoint['data']['json']
            address = body['address']
            frontend_key = body.get('frontend_routing_key', None)
            if frontend_key:
                for routing_key in body.get('routing_keys', []):
                    is_default = routing_key['is_default']
                    key = routing_key['routing_key']
                    endpoint_collection.append(
                        Endpoint(address=address, routing_keys=[key, frontend_key], is_default=is_default)
                    )
            else:
                endpoint_collection.append(
                    Endpoint(address=address, routing_keys=[], is_default=False)
                )
        if not endpoint_collection:
            raise RuntimeError('Endpoints are empty')
        self.__endpoints = endpoint_collection


class AgentEvents(BaseAgentConnection):
    """RPC service.

    Reactive nature of Smart-Contract design
    """

    @classmethod
    def _path(cls):
        return '/events'


class CoProtocolsObserver:
    """https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0003-protocols
    """

    class Condition:
        """Condition is amount of rules that communication actor set to filter response beside message streams
        of coprotocols

        https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0008-message-id-and-threading
        """

        def __init__(self, thid: str):
            """
            :param thid: thread id of responded message
                See docs:  https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0008-message-id-and-threading#threaded-messages
            """
            self.thid = thid

        @property
        def unique_id(self):
            dump = json.dumps({'thid': self.thid}).encode()
            value = hashlib.sha1(dump).hexdigest()
            return value

        def check(self, message: Message) -> bool:
            thread_id = message.get('~thread', {}).get('thid', None)
            return thread_id == self.thid

    def __init__(self, tunnel: AddressedTunnel):
        self.__messages_stream = tunnel
        self.__subscribers = {}

    async def poll(self, timeout: int, cond: Condition) -> bool:
        expires_time = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
        while datetime.datetime.now() < expires_time:
            timedelta = expires_time - datetime.datetime.now()
            timeout = max(timedelta.seconds, 0)
            message = await self.__messages_stream.receive(timeout)


class SubProtocol:

    def __init__(self):
        pass
