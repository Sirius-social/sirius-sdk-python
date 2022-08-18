import json
import uuid
import asyncio

import pytest
import sirius_sdk
from sirius_sdk import Agent
from sirius_sdk.messaging import Message

from tests.helpers import ServerTestSuite
from tests.conftest import get_pairwise2


async def run_sender_with_delay(
        sdk: dict, their_vk: str, endpoint: str, my_vk: str,
        msg: sirius_sdk.aries_rfc.Message, delay: int = 3
):
    async with sirius_sdk.context(sdk['server_address'], sdk['credentials'], sdk['p2p']):
        await asyncio.sleep(delay)
        try:
            await sirius_sdk.send(
                msg, their_vk=their_vk, endpoint=endpoint,
                my_vk=my_vk, routing_keys=[]
            )
        except Exception as e:
            raise


@pytest.mark.asyncio
async def test_message_delivery(test_suite: ServerTestSuite):
    sdk_me = test_suite.get_agent_params('agent1')
    sdk_their = test_suite.get_agent_params('agent2')
    expected_content = 'Hello-' + uuid.uuid4().hex

    mediate_vk_bytes, mediate_sk_bytes = sirius_sdk.encryption.create_keypair()
    mediate_vk = sirius_sdk.encryption.bytes_to_b58(mediate_vk_bytes)
    mediate_sk = sirius_sdk.encryption.bytes_to_b58(mediate_sk_bytes)
    p2p = await get_pairwise2((sdk_me, 'agent1'), (sdk_their, 'agent2'))

    msg = sirius_sdk.aries_rfc.BasicMessage(
        content=expected_content
    )
    fut = asyncio.ensure_future(
        run_sender_with_delay(sdk_me, mediate_vk, p2p.their.endpoint, p2p.me.verkey, msg)
    )

    async with sirius_sdk.context(sdk_their['server_address'], sdk_their['credentials'], sdk_their['p2p']):
        listener = await sirius_sdk.subscribe()
        event = await listener.get_one(timeout=5)
    assert event
    fwd = Message(event['message'])
    assert fwd.protocol == 'routing'
    assert fwd.name == 'forward'
    assert fwd['to'] == mediate_vk
    s, sender_vk, recip_vk = sirius_sdk.encryption.unpack_message(fwd['msg'], mediate_vk, mediate_sk)
    msg = json.loads(s)
    assert msg['content'] == expected_content
    assert sender_vk == p2p.me.verkey
    assert recip_vk == mediate_vk
