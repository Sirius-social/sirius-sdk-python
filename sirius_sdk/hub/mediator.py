import json
import asyncio
import logging
import math
import hashlib
from typing import Union, Optional, List, Dict

import aiohttp

import sirius_sdk
import sirius_sdk.abstract.p2p
from sirius_sdk.abstract.listener import AbstractListener, Event
from sirius_sdk.didcomm import extentions as didcomm_ext
from sirius_sdk.base import BaseConnector, INFINITE_TIMEOUT
from sirius_sdk.abstract.p2p import Endpoint
from sirius_sdk.hub.coprotocols import AbstractP2PCoProtocol
from sirius_sdk.abstract.api import APIRouter, APICoProtocols
from sirius_sdk.errors.exceptions import *
from sirius_sdk.abstract.bus import AbstractBus
from sirius_sdk.messaging import Message, restore_message_instance, Type as MsgType
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.agent.aries_rfc.did_doc import DIDDoc
from sirius_sdk.agent.aries_rfc.mixins import ThreadMixin as AriesThreadMixin
from sirius_sdk.agent.aries_rfc.feature_0753_bus.messages import *
from sirius_sdk.agent.aries_rfc.feature_0212_pickup.messages import *


def qualify_key(key: str) -> str:
    if ':' not in key:
        return f'did:key:{key}'
    else:
        return key


class MediatorConnector(BaseConnector):

    IO_TIMEOUT = 60
    ENC = 'utf-8'

    def __init__(
            self, uri: str, loop: asyncio.AbstractEventLoop = None, timeout: int = IO_TIMEOUT,
            http_headers: dict = None
    ):
        self.__session = aiohttp.ClientSession(
            loop=loop,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers=http_headers
        )
        self._uri = uri
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
        if isinstance(message, Message):
            payload = message.serialize().encode(self.ENC)
        else:
            payload = message
        await self._ws.send_bytes(payload)
        return True


class TunnelMixin:

    async def pack(self, message: Message) -> bytes:
        packed = await sirius_sdk.Crypto.pack_message(
            message=json.dumps(message),
            recipient_verkeys=[self.mediator_verkey],
            sender_verkey=self.my_verkey,
        )
        return packed

    async def unpack(self, jwe: bytes) -> (Optional[Union[Message, bytes]], str, Optional[str]):

        if b'protected' in jwe:
            decrypted = await sirius_sdk.Crypto.unpack_message(jwe)
            message, sender_vk, recip_vk = decrypted['message'], decrypted['sender_verkey'], decrypted['recipient_verkey']
        else:
            message, sender_vk, recip_vk = json.loads(jwe.decode()), None, None

        if type(message) is str:
            payload = json.loads(message)
        elif type(message) is bytes:
            payload = json.loads(message.decode())
        elif type(message) is dict:
            payload = message
        else:
            raise SiriusInvalidMessage('Unexpected message type')
        if 'protected' in payload:
            return message.encode(), sender_vk, recip_vk
        else:
            success, msg = restore_message_instance(payload)
            if success:
                return msg, sender_vk, recip_vk
            else:
                return Message(**payload), sender_vk, recip_vk


class MediatorCoProtocol(TunnelMixin, AbstractP2PCoProtocol):

    def __init__(
            self,
            connector: MediatorConnector, my_verkey: str, mediator_verkey: str,
            time_to_live: int = None
    ):
        super().__init__(time_to_live)
        self.__connector: MediatorConnector = connector
        self._mediator_verkey = mediator_verkey
        self._my_verkey = my_verkey

    @property
    def connector(self) -> MediatorConnector:
        return self.__connector

    @property
    def mediator_verkey(self) -> str:
        return self._mediator_verkey

    @property
    def my_verkey(self) -> str:
        return self._my_verkey

    async def send(self, message: Message):
        # Aries-RFC 0092 https://github.com/hyperledger/aries-rfcs/tree/master/features/0092-transport-return-route
        transport = message.get('~transport', {})
        transport['return_route'] = 'all'
        message['~transport'] = transport
        payload = await self.pack(message)
        await self.connector.write(payload)

    async def get_one(self, timeout: int = None) -> (Optional[Message], str, Optional[str]):
        payload = await self.connector.read(timeout)
        message, sender_vk, recip_vk = await self.unpack(payload)
        return message, sender_vk, recip_vk

    async def switch(self, message: Message) -> (bool, Message):
        await self.send(message)
        msg, _, _ = await self.get_one()
        return True, msg


class MediatorBus(AbstractBus, TunnelMixin):

    BINDINGS_CTX_ID = 'binding.id'

    def __init__(self, connector: MediatorConnector, my_verkey: str, mediator_verkey: str):
        self.__connector: MediatorConnector = connector
        self._mediator_verkey = mediator_verkey
        self._my_verkey = my_verkey
        self.__client_id = str(id(self))
        self.__binding_ids: Dict[str, str] = {}

    @property
    def connector(self) -> MediatorConnector:
        return self.__connector

    @property
    def mediator_verkey(self) -> str:
        return self._mediator_verkey

    @property
    def my_verkey(self) -> str:
        return self._my_verkey

    async def subscribe(self, thid: str) -> bool:
        request = BusSubscribeRequest(cast=BusSubscribeRequest.Cast(thid=thid), parent_thread_id=self.__client_id)
        payload = await self.pack(request)
        await self.connector.write(payload)
        jwe = await self.connector.read()
        resp, _, _ = await self.unpack(jwe)
        self.__validate(resp, expected_class=BusBindResponse)
        if resp.thread_id != thid:
            self.__set_binding_id(thid, resp.binding_id)
        return True

    async def subscribe_ext(self, sender_vk: List[str], recipient_vk: List[str], protocols: List[str]) -> (bool, List[str]):
        binding_id = []
        for _sender_vk in sender_vk:
            for _recipient_vk in recipient_vk:
                for protocol in protocols:
                    thid = self.__binding_id_from_attrs(_sender_vk, _recipient_vk, protocol)
                    success = await self.subscribe(thid)
                    if success:
                        binding_id.append(thid)
        return len(binding_id) > 0, binding_id

    async def unsubscribe(self, thid: str):
        binding_id = self.__pop_binding_id(thid)
        request = BusUnsubscribeRequest(
            thread_id=binding_id or thid,
            need_answer=False,  # don't wait response
        )
        payload = await self.pack(request)
        await self.connector.write(payload)

    async def unsubscribe_ext(self, thids: List[str]):
        request = BusUnsubscribeRequest(
            thread_id=thids,
            need_answer=False,  # don't wait response
            parent_thread_id=self.__client_id
        )
        payload = await self.pack(request)
        await self.connector.write(payload)

    async def publish(self, thid: str, payload: bytes) -> int:
        binding_id = self.__get_binding_id(thid)
        request = BusPublishRequest(thread_id=binding_id or thid, payload=payload)
        payload = await self.pack(request)
        await self.connector.write(payload)
        jwe = await self.connector.read()
        resp, _, _ = await self.unpack(jwe)
        self.__validate(resp, expected_class=BusPublishResponse)
        return resp.recipients_num

    async def get_event(self, timeout: float = None) -> AbstractBus.BytesEvent:
        expire_at = datetime.datetime.now() + datetime.timedelta(seconds=timeout) if timeout is not None else None

        def __in_loop__() -> bool:
            if expire_at is None:
                return True
            else:
                return datetime.datetime.now() <= expire_at

        while __in_loop__():
            if expire_at is None:
                wait_timeout = None
            else:
                dt_diff = expire_at - datetime.datetime.now()
                wait_timeout = dt_diff.total_seconds()

            request = PickUpNoop()
            if wait_timeout is not None:
                request.timing = PickUpNoop.Timing(delay_milli=math.ceil(wait_timeout * 1000))
            else:
                request.timing = PickUpNoop.Timing(delay_milli=5*60 * 1000)  # wait for 5 min by default

            request.please_ack = True
            payload = await self.pack(request)
            await self.connector.write(payload)
            if timeout is None:
                read_timeout = None
            else:
                read_timeout = 1.1*timeout   # Increase if pickup protocol not raise response
            jwe = await self.connector.read(read_timeout)

            resp, sender_vk, recip_vk = await self.unpack(jwe)
            if isinstance(resp, Message):
                thread = ThreadMixin.get_thread(resp)
                if thread and ((thread.pthid == self.__client_id) or (thread.thid == request.id)):
                    if isinstance(resp, BusEvent):
                        return AbstractBus.BytesEvent(thread_id=resp.thread_id, payload=resp.payload)
                    elif isinstance(resp, BusBindResponse):
                        if resp.aborted is True and resp.parent_thread_id == self.__client_id:
                            raise OperationAbortedManually('Bus events awaiting was aborted by user')
                    elif isinstance(resp, BusProblemReport):
                        raise SiriusRPCError(resp.explain)
                    elif isinstance(resp, PickUpProblemReport):
                        if resp.problem_code == PickUpProblemReport.PROBLEM_CODE_TIMEOUT_OCCURRED:
                            if wait_timeout is not None:
                                raise SiriusTimeoutIO
                            else:
                                continue
                        else:
                            raise SiriusRPCError(resp.explain)
                else:
                    logging.warning(
                        f'Bus listener: message was ignored cause of unexpected thread binging, '
                        f'expected pthid: {self.__client_id}'
                    )
                    logging.warning(json.dumps(resp, indent=2, sort_keys=True))
            if isinstance(resp, bytes):
                logging.critical('Unexpected bytes received')
                # fwd, fwd_sender_vk, fwd_recip_vk = await self.unpack(resp)
                # await self.__raise_bus_message(fwd, resp, fwd_sender_vk, fwd_recip_vk)

    async def get_message(self, timeout: float = None) -> AbstractBus.MessageEvent:
        event = await self.get_event(timeout)
        decrypted = await sirius_sdk.Crypto.unpack_message(event.payload)
        message = decrypted['message']
        if isinstance(message, str):
            message = json.loads(message)
        if message.get('@type', None):
            ok, msg = restore_message_instance(decrypted)
            if not ok:
                msg = Message(**message)
            return AbstractBus.MessageEvent(
                thread_id=event.thread_id,
                message=msg,
                sender_verkey=decrypted.get('sender_verkey', None),
                recipient_verkey=decrypted.get('recipient_verkey', None)
            )
        else:
            raise SiriusRPCError('Unexpected message format')

    async def abort(self):
        request = BusUnsubscribeRequest(parent_thread_id=self.__client_id, aborted=True)
        payload = await self.pack(request)
        await self.connector.write(payload)

    @staticmethod
    def __validate(msg: BusOperation, expected_class) -> BusOperation:
        if isinstance(msg, BusProblemReport):
            raise SiriusRPCError(msg.explain)
        elif isinstance(msg, expected_class):
            return msg
        else:
            raise SiriusRPCError(f'Unexpected response type: {msg.__class__.__name__}')

    def __get_binding_id(self, thid: str) -> Optional[str]:
        return self.__binding_ids.get(thid, None)

    def __pop_binding_id(self, thid: str) -> Optional[str]:
        bid = self.__binding_ids.get(thid, None)
        if bid is not None:
            del self.__binding_ids[thid]
        return bid

    def __set_binding_id(self, thid: str, binding_id: str):
        self.__binding_ids[thid] = binding_id

    async def __raise_bus_message(self, decrypted: Message, jwe: bytes, sender_vk, recip_vk):
        if '@type' in decrypted:
            thread = AriesThreadMixin.get_thread(decrypted)
            if thread and thread.thid:
                num = await self.publish(thread.thid, jwe)
                print('')

    @staticmethod
    def __binding_id_from_attrs(sender_vk: Optional[str], recipient_vk: Optional[str], protocol: str) -> str:
        return f'protocol:{sender_vk}/{recipient_vk}/{protocol}'


class MediatorListener(TunnelMixin, AbstractListener):

    def __init__(
            self, connector: MediatorConnector, my_verkey: Optional[str],
            mediator_verkey: Optional[str], pairwise_resolver: AbstractPairwiseList = None
    ):
        self.__connector: MediatorConnector = connector
        self.__pairwise_resolver = pairwise_resolver
        self._mediator_verkey = mediator_verkey
        self._my_verkey = my_verkey

    @property
    def connector(self) -> MediatorConnector:
        return self.__connector

    @property
    def mediator_verkey(self) -> str:
        return self._mediator_verkey

    @property
    def my_verkey(self) -> str:
        return self._my_verkey

    def is_open(self) -> bool:
        return self.__connector.is_open

    async def get_one(self, timeout: int = None) -> Event:
        if timeout is None:
            wait_timeout = INFINITE_TIMEOUT
        else:
            wait_timeout = timeout
        payload = await self.connector.read(timeout=wait_timeout)
        message, sender_vk, recip_vk = await self.unpack(payload)
        if sender_vk is not None and self.__pairwise_resolver is not None:
            p2p = await self.__pairwise_resolver.load_for_verkey(sender_vk)
        else:
            p2p = None
        kwargs = {
           '@type': 'https://didcomm.org/sirius_rpc/1.0/event',
           'message': message,
           'recipient_verkey': recip_vk,
           'sender_verkey': sender_vk,
           'jwe': payload
        }
        event = Event(pairwise=p2p, **kwargs)
        return event


class Mediator(APIRouter, APICoProtocols):

    FIREBASE_SERVICE_TYPE = 'FCMService'
    DEFAULT_GROUP_ID = 'default'
    # Reserved group-id
    COPROTOCOLS_GROUP_ID = 'coprotocols_group_id_for_decrypt'

    def __init__(
            self, uri: str, my_verkey: str, mediator_verkey: str,
            firebase_device_id: str = None,
            mediator_label: str = None,
            routing_keys: List[str] = None,
            timeout: int = MediatorConnector.IO_TIMEOUT,
            pairwise_resolver: AbstractPairwiseList = None
    ):
        self.__uri = uri
        self.__timeout = timeout
        self.__pairwise_resolver = pairwise_resolver
        self._connector = MediatorConnector(
            uri=self.__uri, timeout=self.__timeout,
            http_headers={
                didcomm_ext.return_route.HEADER_NAME: didcomm_ext.return_route.RouteType.ALL.value
            }
        )
        self.__my_verkey = my_verkey
        self.__mediator_verkey = mediator_verkey
        self.__mediator_label = mediator_label
        self._coprotocol = MediatorCoProtocol(
            connector=self._connector,
            my_verkey=self.__my_verkey,
            mediator_verkey=self.__mediator_verkey,
            time_to_live=self.__timeout
        )
        my_did_bytes = sirius_sdk.encryption.did_from_verkey(
            sirius_sdk.encryption.b58_to_bytes(my_verkey)
        )
        self.me = sirius_sdk.abstract.p2p.Pairwise.Me(
            did=sirius_sdk.encryption.bytes_to_b58(my_did_bytes),
            verkey=my_verkey
        )
        self._my_did = sirius_sdk.encryption.did_from_verkey(
            sirius_sdk.encryption.b58_to_bytes(my_verkey)
        )
        self.firebase_device_id = firebase_device_id
        self._mediator_invitation = sirius_sdk.aries_rfc.Invitation(
            label=self.__mediator_label or 'Mediator',
            recipient_keys=[self.__mediator_verkey],
            endpoint=uri
        )
        self._endpoints = []
        self.__is_connected = False
        self.__did_doc = None
        if routing_keys is None:
            routing_keys = []
        self.__routing_keys = [qualify_key(key) for key in routing_keys]
        self.__endpoints: List[sirius_sdk.abstract.p2p.Endpoint] = []
        self.__bus: Optional[AbstractBus] = None

    def copy(self) -> "Mediator":
        inst = Mediator(
            uri=self.__uri, my_verkey=self.__my_verkey, mediator_verkey=self.__mediator_verkey,
            mediator_label=self.__mediator_label, routing_keys=self.__routing_keys, timeout=self.__timeout,
            pairwise_resolver=self.__pairwise_resolver
        )
        return inst

    @property
    def is_connected(self) -> bool:
        return self.__is_connected

    @property
    def did_doc(self) -> Optional[dict]:
        return self.__did_doc

    @property
    def endpoints(self) -> List[sirius_sdk.abstract.p2p.Endpoint]:
        return self.__endpoints

    @property
    def bus(self) -> AbstractBus:
        return self.__bus

    async def connect(self):
        if self.__is_connected:
            return
        # Run P2P connection establishment according Aries-RFC0160
        if not self._connector.is_open:
            await self._connector.open()
        try:
            self.__is_connected = True
            success, mediator_did_doc = await self.__connect_to_mediator(
                endpoint=didcomm_ext.return_route.URI_QUEUE_TRANSPORT,
                firebase_device_id=self.firebase_device_id,
                group_id='off'
            )
            if success:
                # 3. P2P successfully established
                self.__did_doc = mediator_did_doc
                if self.__routing_keys:
                    # 4. Actualize routing_keys
                    keys_request = sirius_sdk.aries_rfc.KeylistQuery()
                    success, keys_response = await self._coprotocol.switch(keys_request)
                    if success:
                        mediator_mediate_keys = keys_response['keys']
                        keys_to_add = [key for key in self.__routing_keys if key not in mediator_mediate_keys]
                        command = sirius_sdk.aries_rfc.KeylistUpdate(
                            updates=[
                                sirius_sdk.aries_rfc.KeylistAddAction(recipient_key=key)
                                for key in keys_to_add
                            ]
                        )
                        success, update_response = await self._coprotocol.switch(command)
                        if not success:
                            raise SiriusRPCError('Error while updating mediator keys list')
                    else:
                        raise SiriusRPCError('Error while requesting mediator keys list')
                # Final: grant endpoint
                mediate_request = sirius_sdk.aries_rfc.MediateRequest()
                success, mediate_grant = await self._coprotocol.switch(mediate_request)
                if success:
                    routing_keys = self.__routing_keys
                    routing_keys.extend(mediate_grant['routing_keys'])
                    self.__endpoints.append(
                        sirius_sdk.abstract.p2p.Endpoint(
                            address=mediate_grant['endpoint'],
                            routing_keys=routing_keys,
                            is_default=True
                        )
                    )
                    self.__bus = MediatorBus(
                        connector=self._connector,
                        my_verkey=self._coprotocol.my_verkey,
                        mediator_verkey=self._coprotocol.mediator_verkey
                    )
                else:
                    raise SiriusRPCError('Error while granting mediate endpoint')
            else:
                raise SiriusConnectionClosed()
        except BaseSiriusException:
            await self.disconnect()
            raise

    async def disconnect(self):
        if self.__is_connected:
            await self._connector.close()
            self.__is_connected = False
            self.__did_doc = None
            self.__bus = None

    async def get_endpoints(self) -> List[Endpoint]:
        return self.__endpoints

    async def subscribe(self, group_id: str = None) -> AbstractListener:
        # Re-Open RPC
        await self._connector.close()
        await self._connector.open()
        # Redeclare Group-ID in DIDDoc to re-schedule downstream
        success, diddoc = await self.__connect_to_mediator(
            endpoint='ws://',
            group_id=group_id or self.DEFAULT_GROUP_ID
        )
        if success:
            diddoc = DIDDoc(diddoc)
            mediator_services = diddoc.extract_service(high_priority=True, type_='MediatorService')
            uri = mediator_services['serviceEndpoint']
            conn = MediatorConnector(uri)
            await conn.open()
            listener = MediatorListener(
                connector=conn,
                my_verkey=None,
                mediator_verkey=None
            )
            return listener
        else:
            raise SiriusRPCError('Error while configure load-balancer')

    async def spawn_coprotocol(self) -> AbstractBus:
        bus = MediatorBus(
            connector=self._connector,
            my_verkey=self._coprotocol.my_verkey,
            mediator_verkey=self._coprotocol.mediator_verkey
        )
        return bus

    async def __connect_to_mediator(
            self, endpoint: str = didcomm_ext.return_route.URI_QUEUE_TRANSPORT,
            firebase_device_id: str = None, group_id: str = None
    ) -> (bool, Optional[dict]):
        # Run P2P connection establishment according Aries-RFC0160
        # - RFC: https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
        # - recipient declare endpoint address as "ws://" that means communication is established over duplex channel
        #   see details: https://github.com/hyperledger/aries-rfcs/tree/main/features/0092-transport-return-route
        state_machine = sirius_sdk.aries_rfc.Invitee(
            me=self.me,
            my_endpoint=sirius_sdk.abstract.p2p.Endpoint(
                address=didcomm_ext.return_route.URI_QUEUE_TRANSPORT,
                routing_keys=[]
            ),
            coprotocol=self._coprotocol
        )
        # 1. Recipient DIDDoc contains Firebase device id inside service with type "FCMService"
        did_doc = sirius_sdk.aries_rfc.ConnRequest.build_did_doc(
            did=self.me.did,
            verkey=self.me.verkey,
            endpoint=endpoint
        )
        if group_id is not None:
            services_num = len(did_doc['service'])
            for n in range(services_num):
                did_doc['service'][n]['group_id'] = group_id
        did_doc_extra = {'service': did_doc['service']}
        if firebase_device_id:
            did_doc_extra['service'].append({
                "id": 'did:peer:' + self.me.did + ";indy",
                "type": self.FIREBASE_SERVICE_TYPE,
                "recipientKeys": [],
                "priority": 1,
                "serviceEndpoint": firebase_device_id
            })
        success, p2p = await state_machine.create_connection(
            invitation=self._mediator_invitation,
            my_label=f'did:peer:{self.me.did}',
            did_doc=did_doc_extra
        )
        if success:
            return True, p2p.their.did_doc
        else:
            return False, None
