import asyncio

import uuid
import json
import os.path
import pathlib

import pyqrcode

import sirius_sdk
from sirius_sdk.abstract.api import *
from sirius_sdk.errors.exceptions import SiriusTransportError
from sirius_sdk.messaging.transport import EndpointTransport
from sirius_sdk.messaging.forwarding import forward_wired

from .inmemory_bus import InMemoryBus


class APIDefault(APIContents, APITransport, APICoProtocols):

    DEF_TIMEOUT = 30

    def __init__(self, crypto: APICrypto = None):
        self.__transport = EndpointTransport(keepalive_timeout=self.DEF_TIMEOUT)
        self.__crypto = crypto or sirius_sdk.Crypto

    async def send(
            self, message: Message, their_vk: Union[List[str], str],
            endpoint: str, my_vk: Optional[str] = None, routing_keys: Optional[List[str]] = None
    ):
        if their_vk is None:
            their_vk = []
        if isinstance(their_vk, str):
            their_vk = [their_vk]
        if their_vk:
            payload = await self.__crypto.pack_message(
                message=json.dumps(message),
                recipient_verkeys=their_vk,
                sender_verkey=my_vk
            )
            their_vk = their_vk[0] if isinstance(their_vk, list) else their_vk
        else:
            payload = json.dumps(message).encode()
            their_vk = None

        if routing_keys:
            if my_vk:
                payload = await forward_wired(payload, their_vk, routing_keys, self.__crypto, my_vk)
            else:
                payload = await forward_wired(payload, their_vk, routing_keys)
        if routing_keys or their_vk:
            content_type = 'application/ssi-agent-wire'
        else:
            content_type = 'application/json'

        ok, body = await self.__transport.send(
            msg=payload, endpoint=endpoint, timeout=self.DEF_TIMEOUT, content_type=content_type
        )
        if not ok:
            raise SiriusTransportError(body)

    async def send_to(self, message: Message, to: Pairwise):
        await self.send(
            message=message,
            their_vk=to.their.verkey,
            endpoint=to.their.endpoint,
            my_vk=to.me.verkey,
            routing_keys=to.their.routing_keys
        )

    async def send_batched(self, message: Message, batches: List[RoutingBatch]) -> List[Tuple[bool, str]]:
        jobs = []
        for batch in batches:
            routing_keys = batch.get('routing_keys', [])
            recipient_verkeys = batch.get('recipient_verkeys', [])
            sender_verkey = batch.get('sender_verkey', None)
            endpoint_address = batch['endpoint_address']
            if routing_keys or recipient_verkeys:
                content_type = 'application/ssi-agent-wire'
            else:
                content_type = 'application/json'
            payload = await self.__crypto.pack_message(
                message=json.dumps(message),
                recipient_verkeys=recipient_verkeys,
                sender_verkey=sender_verkey
            )
            their_vk = recipient_verkeys[0] if len(recipient_verkeys) == 1 else recipient_verkeys
            if routing_keys:
                if sender_verkey:
                    payload = await forward_wired(
                        payload, their_vk, routing_keys, self.__crypto, sender_verkey
                    )
                else:
                    payload = await forward_wired(payload, their_vk, routing_keys)

            async_routine = self.__transport.send(payload, endpoint_address, self.DEF_TIMEOUT, content_type)
            jobs.append(async_routine)
        # Run simultaneously
        results = await asyncio.gather(*jobs)
        return list(results)

    async def generate_qr_code(self, value: str) -> str:
        qr = pyqrcode.create(content=value)
        base_dir = os.path.abspath(os.curdir)
        path = os.path.join(base_dir, f'qr_code_{uuid.uuid4().hex}.svg')
        qr.svg(path, scale=2)
        url = pathlib.Path(path).as_uri()
        return url

    async def spawn_coprotocol(self) -> AbstractBus:
        return InMemoryBus()
