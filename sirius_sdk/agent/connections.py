import json
import aiohttp
import asyncio
import datetime
from abc import ABC, abstractmethod
from typing import List, Any, Union, Optional

from sirius_sdk.base import WebSocketConnector
from sirius_sdk.encryption import P2PConnection
from sirius_sdk.rpc import AddressedTunnel, build_request, Future
from sirius_sdk.messaging import Message, Type as MessageType
from sirius_sdk.errors.exceptions import *
from sirius_sdk.agent.transport import http_send


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

    def __init__(
            self, server_address: str, credentials: bytes,
            p2p: P2PConnection, timeout: int = IO_TIMEOUT, loop: asyncio.AbstractEventLoop = None
    ):
        self._connector = WebSocketConnector(
            server_address=server_address,
            path=self._path(),
            credentials=credentials,
            timeout=timeout,
            loop=loop
        )
        self._p2p = p2p
        self._timeout = timeout

    def __del__(self):
        asyncio.ensure_future(self.close())

    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, value: int):
        if value is None:
            self._timeout = None
        elif value > 0:
            self._timeout = value
        else:
            raise RuntimeError('Timeout must be > 0')

    @property
    def is_open(self):
        return self._connector.is_open

    async def close(self):
        await self._connector.close()

    @classmethod
    async def create(
            cls, server_address: str, credentials: bytes,
            p2p: P2PConnection, timeout: int=IO_TIMEOUT, loop: asyncio.AbstractEventLoop=None
    ):
        instance = cls(server_address, credentials, p2p, timeout, loop)
        await instance._connector.open()
        payload = await instance._connector.read(timeout=timeout)
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


class RoutingBatch(dict):

    def __init__(
            self, their_vk: Union[List[str], str], endpoint: str,
            my_vk: Optional[str] = None, routing_keys: Optional[List[str]] = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if isinstance(their_vk, str):
            self['recipient_verkeys'] = [their_vk]
        else:
            self['recipient_verkeys'] = their_vk
        self['endpoint_address'] = endpoint
        self['sender_verkey'] = my_vk
        self['routing_keys'] = routing_keys or []


class AgentRPC(BaseAgentConnection):
    """RPC service.

    Proactive form of Smart-Contract design
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__tunnel_rpc = None
        self.__tunnel_coprotocols = None
        self.__endpoints = []
        self.__networks = []
        self.__websockets = {}
        self.__prefer_agent_side = True
        self.__tcp_connector = aiohttp.TCPConnector(ssl=False, keepalive_timeout=60)

    @property
    def endpoints(self) -> List[Endpoint]:
        return self.__endpoints

    @property
    def networks(self) -> List[str]:
        return self.__networks

    async def remote_call(
            self, msg_type: str, params: dict = None, wait_response: bool = True, reconnect_on_error: bool = True
    ) -> Any:
        """Call Agent services

        :param msg_type:
        :param params:
        :param wait_response: wait for response
        :param reconnect_on_error: try reconnect if server was closed recources
        :return:
        """
        try:
            if not self._connector.is_open:
                raise SiriusConnectionClosed('Open agent connection at first')
            if self._timeout:
                expiration_time = datetime.datetime.now() + datetime.timedelta(seconds=self._timeout)
            else:
                expiration_time = None
            future = Future(
                tunnel=self.__tunnel_rpc,
                expiration_time=expiration_time
            )
            request = build_request(
                msg_type=msg_type,
                future=future,
                params=params or {}
            )
            msg_typ = MessageType.from_str(msg_type)
            encrypt = msg_typ.protocol not in ['admin', 'microledgers']
            if not await self.__tunnel_rpc.post(message=request, encrypt=encrypt):
                raise SiriusRPCError()
            if wait_response:
                success = await future.wait(timeout=self._timeout)
                if success:
                    if future.has_exception():
                        future.raise_exception()
                    else:
                        return future.get_value()
                else:
                    raise SiriusTimeoutRPC()
        except SiriusConnectionClosed:
            if reconnect_on_error:
                await self._reopen()
                return await self.remote_call(msg_type, params, wait_response, reconnect_on_error=False)
            else:
                raise
        
    async def send_message(
            self, message: Message,
            their_vk: Union[List[str], str], endpoint: str,
            my_vk: Optional[str], routing_keys: Optional[List[str]],
            coprotocol: bool = False
    ) -> Optional[Message]:
        """Send Message to other Indy compatible agent
        
        :param message: message
        :param their_vk: Verkey of recipients
        :param endpoint: Endpoint Address of recipient
        :param my_vk: Verkey of sender (None for anocrypt mode)
        :param routing_keys: Routing keys if it is exists
        :param coprotocol: True if message is part of co-protocol stream
            See:
             - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0003-protocols
             - https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0008-message-id-and-threading
        :return: Response message if coprotocol is True
        """
        if not self._connector.is_open:
            raise SiriusConnectionClosed('Open agent connection at first')
        if isinstance(their_vk, str):
            recipient_verkeys = [their_vk]
        else:
            recipient_verkeys = their_vk
        params = {
            'message': message,
            'routing_keys': routing_keys or [],
            'recipient_verkeys': recipient_verkeys,
            'sender_verkey': my_vk
        }
        if self.__prefer_agent_side:
            params['timeout'] = self.timeout
            params['endpoint_address'] = endpoint
            ok, body = await self.remote_call(
                msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/send_message',
                params=params
            )
        else:
            wired = await self.remote_call(
                msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/prepare_message_for_send',
                params=params
            )
            if endpoint.startswith('ws://') or endpoint.startswith('wss://'):
                ws = await self.__get_websocket(endpoint)
                await ws.send_bytes(wired)
                ok, body = True, b''
            else:
                ok, body = await http_send(wired, endpoint, timeout=self.timeout, connector=self.__tcp_connector)
            body = body.decode()
        if not ok:
            raise SiriusRPCError(body)
        else:
            if coprotocol:
                response = await self.read_protocol_message()
                return response
            else:
                return None

    async def send_message_batched(self, message: Message, batches: List[RoutingBatch]) -> List[Any]:
        if not self._connector.is_open:
            raise SiriusConnectionClosed('Open agent connection at first')
        params = {
            'message': message,
            'timeout': self.timeout,
            'batches': batches,
        }
        results = await self.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/send_message_batched',
            params=params
        )
        return results

    async def read_protocol_message(self) -> Message:
        response = await self.__tunnel_coprotocols.receive(timeout=self._timeout)
        return response

    async def start_protocol_with_threading(self, thid: str, ttl: int=None):
        await self.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/start_protocol',
            params={
                'thid': thid,
                'channel_address': self.__tunnel_coprotocols.address,
                'ttl': ttl
            }
        )

    async def start_protocol_with_threads(self, threads: List[str], ttl: int=None):
        await self.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/start_protocol',
            params={
                'threads': threads,
                'channel_address': self.__tunnel_coprotocols.address,
                'ttl': ttl
            }
        )

    async def start_protocol_for_p2p(self, sender_verkey: str, recipient_verkey: str, protocols: List[str], ttl: int=None):
        await self.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/start_protocol',
            params={
                'sender_verkey': sender_verkey,
                'recipient_verkey': recipient_verkey,
                'protocols': protocols,
                'channel_address': self.__tunnel_coprotocols.address,
                'ttl': ttl
            }
        )

    async def stop_protocol_with_threading(self, thid: str, off_response: bool=False):
        await self.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/stop_protocol',
            params={
                'thid': thid,
                'off_response': off_response
            },
            wait_response=not off_response
        )

    async def stop_protocol_with_threads(self, threads: List[str], off_response: bool=False):
        await self.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/stop_protocol',
            params={
                'threads': threads,
                'off_response': off_response
            },
            wait_response=not off_response
        )

    async def stop_protocol_for_p2p(
            self, sender_verkey: str, recipient_verkey: str, protocols: List[str], off_response: bool=False
    ):
        await self.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/stop_protocol',
            params={
                'sender_verkey': sender_verkey,
                'recipient_verkey': recipient_verkey,
                'protocols': protocols,
                'off_response': off_response
            },
            wait_response=not off_response
        )

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
        # Extract Networks
        self.__networks = context.get('~networks', [])

    async def _reopen(self):
        await self._connector.reopen()
        payload = await self._connector.read(timeout=1)
        context = Message.deserialize(payload.decode())
        await self._setup(context)

    async def close(self):
        await super().close()
        for ws, session in self.__websockets.values():
            await ws.close()
            await session.close()

    async def __get_websocket(self, url: str):
        tup = self.__websockets.get(url, None)
        if tup is None:
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
            ws = await session.ws_connect(url=url)
            self.__websockets[url] = (ws, session)
        else:
            ws, session = tup
            if ws.closed:
                ws = session.ws_connect(url=url)
                self.__websockets[url] = (ws, session)
        return ws


class AgentEvents(BaseAgentConnection):
    """RPC service.

    Reactive nature of Smart-Contract design
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__tunnel = None
        self.__balancing_group = None

    @property
    def balancing_group(self) -> str:
        return self.__balancing_group

    async def pull(self, timeout: int=None) -> Message:
        if not self._connector.is_open:
            raise SiriusConnectionClosed('Open agent connection at first')
        data = await self._connector.read(timeout=timeout)
        try:
            payload = json.loads(data.decode(self._connector.ENC))
        except json.JSONDecodeError:
            raise SiriusInvalidPayloadStructure()
        if 'protected' in payload:
            message = self._p2p.unpack(payload)
            return Message(message)
        else:
            return Message(payload)

    @classmethod
    def _path(cls):
        return '/events'

    async def _setup(self, context: Message):
        # Extract load balancing info
        balancing = context.get('~balancing', [])
        for balance in balancing:
            if balance['id'] == 'kafka':
                self.__balancing_group = balance['data']['json']['group_id']
