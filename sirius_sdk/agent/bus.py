import datetime
import json
import math
from typing import Dict

from sirius_sdk.messaging import Message, Type as MsgType
from sirius_sdk.abstract.bus import AbstractBus
from sirius_sdk.encryption import P2PConnection
from sirius_sdk.base import WebSocketConnector, INFINITE_TIMEOUT
from sirius_sdk.errors.exceptions import SiriusRPCError, SiriusTimeoutIO, OperationAbortedManually
from sirius_sdk.messaging import restore_message_instance

from .aries_rfc.feature_0753_bus.messages import *


class RpcBus(AbstractBus):

    IO_TIMEOUT = 15

    def __init__(self, connector: WebSocketConnector, p2p: P2PConnection):
        self.__connector: WebSocketConnector = connector
        self.__binding_ids: Dict[str, str] = {}
        self.__p2p = p2p
        self.__client_id = str(id(self))

    async def subscribe(self, thid: str) -> bool:
        request = BusSubscribeRequest(cast=BusSubscribeRequest.Cast(thid=thid), client_id=self.__client_id)
        resp = await self.__rfc(request)
        self.__validate(resp, expected_class=BusBindResponse)
        assert isinstance(resp, BusBindResponse)
        if resp.binding_id != thid:
            self.__set_binding_id(thid, resp.binding_id)
        return True

    async def subscribe_ext(self, sender_vk: List[str], recipient_vk: List[str], protocols: List[str]) -> (bool, List[str]):
        request = BusSubscribeRequest(
            cast=BusSubscribeRequest.Cast(
                sender_vk=sender_vk,
                recipient_vk=recipient_vk,
                protocols=protocols
            ),
            client_id=self.__client_id
        )
        resp = await self.__rfc(request)
        self.__validate(resp, expected_class=BusBindResponse)
        assert isinstance(resp, BusBindResponse)
        if isinstance(resp.binding_id, str):
            binding_ids = [resp.binding_id]
        else:
            binding_ids = resp.binding_id
        return True, binding_ids

    async def unsubscribe(self, thid: str):
        binding_id = self.__pop_binding_id(thid) or thid
        request = BusUnsubscribeRequest(binding_id=binding_id, need_answer=False)
        await self.__rfc(request, wait_response=False)

    async def unsubscribe_ext(self, binding_ids: List[str]):
        actual_binding_ids = []
        for bid in binding_ids:
            actual_bid = self.__pop_binding_id(bid) or bid
            actual_binding_ids.append(actual_bid)
        request = BusUnsubscribeRequest(
            binding_id=actual_binding_ids,
            need_answer=False  # don't wait response
        )
        await self.__rfc(request, wait_response=False)

    async def publish(self, thid: str, payload: bytes) -> int:
        binding_id = self.__get_binding_id(thid) or thid
        request = BusPublishRequest(binding_id=binding_id, payload=payload)
        resp = await self.__rfc(request)
        self.__validate(resp, expected_class=BusPublishResponse)
        assert isinstance(resp, BusPublishResponse)
        return resp.recipients_num

    async def get_event(self, timeout: int = None) -> AbstractBus.BytesEvent:

        if timeout is not None:
            wait_timeout = math.ceil(timeout)
            cut_stamp = datetime.datetime.now() + datetime.timedelta(seconds=wait_timeout)
        else:
            wait_timeout = INFINITE_TIMEOUT
            cut_stamp = None

        while True:
            payload = await self.__connector.read(wait_timeout)
            ok, resp = restore_message_instance(json.loads(payload.decode()))
            if ok:
                if isinstance(resp, BusEvent):
                    return AbstractBus.BytesEvent(binding_id=resp.binding_id, payload=resp.payload)
                elif isinstance(resp, BusBindResponse):
                    if resp.aborted is True and resp.client_id == self.__client_id:
                        raise OperationAbortedManually('Bus events awaiting was aborted by user')
                elif isinstance(resp, BusProblemReport):
                    raise SiriusRPCError(resp.explain)
            if wait_timeout != INFINITE_TIMEOUT:
                _ = (cut_stamp - datetime.datetime.now()).total_seconds()
                wait_timeout = math.ceil(_)
                if wait_timeout <= 0:
                    raise SiriusTimeoutIO

    async def get_message(self, timeout: float = None) -> AbstractBus.MessageEvent:
        event = await self.get_event(timeout)
        decrypted = self.__p2p.unpack(event.payload)
        if decrypted.get('@type', None):
            msg_typ = MsgType.from_str(decrypted['@type'])
            if msg_typ.protocol == 'sirius_rpc' and msg_typ.name == 'event' and 'message' in decrypted:
                ok, msg = restore_message_instance(decrypted['message'])
                if not ok:
                    msg = Message(**decrypted['message'])

                return AbstractBus.MessageEvent(
                    binding_id=event.binding_id,
                    message=msg,
                    sender_verkey=decrypted.get('sender_verkey', None),
                    recipient_verkey=decrypted.get('recipient_verkey', None)
                )
        else:
            raise SiriusRPCError('Unexpected message format')

    async def abort(self):
        request = BusUnsubscribeRequest(client_id=self.__client_id, aborted=True)
        await self.__rfc(request, wait_response=False)

    async def __rfc(self, request: BusOperation, wait_response: bool = True) -> Optional[BusOperation]:
        await self.__connector.write(request)
        if wait_response:
            payload = await self.__connector.read(timeout=self.IO_TIMEOUT)
            ok, resp = restore_message_instance(json.loads(payload.decode()))
            if ok:
                self.__validate(resp, expected_class=BusOperation)
                return resp
            else:
                raise SiriusRPCError('Unexpected response format')
        else:
            return None

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
