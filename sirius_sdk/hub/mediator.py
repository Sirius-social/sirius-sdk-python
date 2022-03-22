import json
import asyncio
import logging
from typing import Union, Optional, List

import aiohttp

import sirius_sdk
from sirius_sdk.didcomm import extentions as didcomm_ext
from sirius_sdk.base import BaseConnector
from sirius_sdk import AbstractP2PCoProtocol
from sirius_sdk.errors.exceptions import *
from sirius_sdk.messaging import Message, restore_message_instance


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


class MediatorCoProtocol(AbstractP2PCoProtocol):

    def __init__(
            self,
            connector: MediatorConnector, my_verkey: str, mediator_verkey: str,
            time_to_live: int = None
    ):
        super().__init__(time_to_live)
        self.__connector: MediatorConnector = connector
        self._mediator_verkey = mediator_verkey
        self._my_verkey = my_verkey

    async def send(self, message: Message):
        # Aries-RFC 0092 https://github.com/hyperledger/aries-rfcs/tree/master/features/0092-transport-return-route
        transport = message.get('~transport', {})
        transport['return_route'] = 'all'
        message['~transport'] = transport

        payload = await sirius_sdk.Crypto.pack_message(
            message=json.dumps(message),
            recipient_verkeys=[self._mediator_verkey],
            sender_verkey=self._my_verkey,
        )
        await self.__connector.write(payload)

    async def get_one(self) -> (Optional[Message], str, Optional[str]):
        payload = await self.__connector.read()
        message, sender_vk, recip_vk = await sirius_sdk.Crypto.unpack_message(payload)
        if type(message) is str:
            payload = json.loads(message)
        elif type(message) is bytes:
            payload = json.loads(message.decode())
        elif type(message) is dict:
            payload = message
        else:
            raise SiriusInvalidMessage('Unexpected message type')
        success, msg = restore_message_instance(payload)
        if success:
            return msg, sender_vk, recip_vk
        else:
            return Message(**payload), sender_vk, recip_vk

    async def switch(self, message: Message) -> (bool, Message):
        await self.send(message)
        msg, _, _ = await self.get_one()
        return True, msg


class Mediator:

    FIREBASE_SERVICE_TYPE = 'FCMService'

    def __init__(
            self, uri: str, my_verkey: str, mediator_verkey: str,
            firebase_device_id: str = None,
            mediator_label: str = None,
            routing_keys: List[str] = None,
            timeout: int = MediatorConnector.IO_TIMEOUT
    ):
        self._connector = MediatorConnector(
            uri=uri, timeout=timeout,
            http_headers={
                didcomm_ext.return_route.HEADER_NAME: didcomm_ext.return_route.RouteType.ALL.value
            }
        )
        self._coprotocol = MediatorCoProtocol(
            connector=self._connector,
            my_verkey=my_verkey,
            mediator_verkey=mediator_verkey,
            time_to_live=timeout
        )
        my_did_bytes = sirius_sdk.encryption.did_from_verkey(
            sirius_sdk.encryption.b58_to_bytes(my_verkey)
        )
        self.me = sirius_sdk.Pairwise.Me(
            did=sirius_sdk.encryption.bytes_to_b58(my_did_bytes),
            verkey=my_verkey
        )
        self._my_did = sirius_sdk.encryption.did_from_verkey(
            sirius_sdk.encryption.b58_to_bytes(my_verkey)
        )
        self.firebase_device_id = firebase_device_id
        self._mediator_invitation = sirius_sdk.aries_rfc.Invitation(
            label=mediator_label or 'Mediator',
            recipient_keys=[mediator_verkey],
            endpoint=uri
        )
        self._endpoints = []
        self.__is_connected = False
        self.__did_doc = None
        if routing_keys is None:
            routing_keys = []
        self.__routing_keys = [qualify_key(key) for key in routing_keys]
        self.__endpoints: List[sirius_sdk.Endpoint] = []

    @property
    def is_connected(self) -> bool:
        return self.__is_connected

    @property
    def did_doc(self) -> Optional[dict]:
        return self.__did_doc

    @property
    def endpoints(self) -> List[sirius_sdk.Endpoint]:
        return self.__endpoints

    async def connect(self):
        if self.__is_connected:
            return
        # Run P2P connection establishment according Aries-RFC0160
        # - RFC: https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
        # - recipient declare endpoint address as "ws://" that means communication is established over duplex channel
        #   see details: https://github.com/hyperledger/aries-rfcs/tree/main/features/0092-transport-return-route
        state_machine = sirius_sdk.aries_rfc.Invitee(
            me=self.me,
            my_endpoint=sirius_sdk.Endpoint(address=didcomm_ext.return_route.URI_QUEUE_TRANSPORT, routing_keys=[]),
            coprotocol=self._coprotocol
        )
        # 1. Recipient DIDDoc contains Firebase device id inside service with type "FCMService"
        did_doc = sirius_sdk.aries_rfc.ConnRequest.build_did_doc(
            did=self.me.did,
            verkey=self.me.verkey,
            endpoint=didcomm_ext.return_route.URI_QUEUE_TRANSPORT
        )
        did_doc_extra = {'service': did_doc['service']}
        if self.firebase_device_id:
            did_doc_extra['service'].append({
                "id": 'did:peer:' + self.me.did + ";indy",
                "type": self.FIREBASE_SERVICE_TYPE,
                "recipientKeys": [],
                "priority": 1,
                "serviceEndpoint": self.firebase_device_id
            })
        # 2. Establish connection with Mediator
        if not self._connector.is_open:
            await self._connector.open()
        try:
            self.__is_connected = True
            success, p2p = await state_machine.create_connection(
                invitation=self._mediator_invitation,
                my_label=f'did:peer:{self.me.did}',
                did_doc=did_doc_extra
            )
            if success:
                # 3. P2P successfully established
                self.__did_doc = p2p.their.did_doc
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
                        sirius_sdk.Endpoint(
                            address=mediate_grant['endpoint'],
                            routing_keys=routing_keys,
                            is_default=True
                        )
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
