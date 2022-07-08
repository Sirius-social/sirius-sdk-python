import json
import uuid
from typing import Optional

from sirius_sdk.abstract.api import APICrypto
from sirius_sdk.encryption import pack_message as default_pack_message_util, b58_to_bytes


FORWARD = 'https://didcomm.org/routing/1.0/forward'
ENCODING = 'ascii'


async def forward_wired(
        payload: bytes, their_vk: Optional[str], routing_keys: list,
        crypto: APICrypto = None, my_vk: str = None
) -> bytes:
    if my_vk:
        if crypto is None:
            raise RuntimeError('You must pass crypto if my_vk is filled')
    keys_map = {}
    for n in range(len(routing_keys) - 1, 0, -1):  # example: IF routing_keys = ['k1', 'k2', 'k3'] THEN n = [2,1]
        outer_key = routing_keys[n]
        inner_key = routing_keys[n - 1]
        keys_map[outer_key] = inner_key
    keys_map[routing_keys[0]] = their_vk

    for outer_key in routing_keys:
        inner_key = keys_map[outer_key]
        outer_key_bytes = b58_to_bytes(outer_key)
        forwarded = {
            '@id': uuid.uuid4().hex,
            '@type': FORWARD,
            'to': inner_key,
            'msg': json.loads(payload.decode(ENCODING))
        }
        if my_vk:
            payload = await crypto.pack_message(
                json.dumps(forwarded),
                recipient_verkeys=[outer_key],
                sender_verkey=my_vk
            )
        else:
            payload = default_pack_message_util(
                message=json.dumps(forwarded),
                to_verkeys=[outer_key_bytes]
            )
    return payload
