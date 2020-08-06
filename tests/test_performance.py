import uuid
from datetime import datetime

import pytest

from sirius_sdk import Agent
from sirius_sdk.messaging import Message
from .conftest import get_pairwise


TEST_ITERATIONS = 100


@pytest.mark.asyncio
async def test_send_message(agent1: Agent, agent2: Agent):
    await agent1.open()
    await agent2.open()
    try:
        a2b = await get_pairwise(agent1, agent2)
        b2a = await get_pairwise(agent2, agent1)
        listener = await agent2.subscribe()

        print('\n>START')
        stamp1 = datetime.now()
        for n in range(TEST_ITERATIONS):
            msg = Message({
                '@id': 'message-id-' + uuid.uuid4().hex,
                '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test/1.0/message',
                "comment": "Hi. Are you listening?",
                "response_requested": True
            })
            await agent1.send_to(msg, a2b)
            resp = await listener.get_one()
            assert resp.message['@id'] == msg['@id']
        print('\n>STOP')
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        print(f'>timeout: {delta.seconds}')
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_send_message_via_transport(agent1: Agent, agent2: Agent):
    await agent1.open()
    await agent2.open()
    try:
        a2b = await get_pairwise(agent1, agent2)
        b2a = await get_pairwise(agent2, agent1)
        thread_id = 'thread-' + uuid.uuid4().hex
        transport_for_a = await agent1.spawn(thread_id, a2b)
        await transport_for_a.start()
        transport_for_b = await agent2.spawn(thread_id, b2a)
        await transport_for_b.start()

        print('\n>START')
        stamp1 = datetime.now()
        for n in range(TEST_ITERATIONS):
            msg = Message({
                '@id': 'message-id-' + uuid.uuid4().hex,
                '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test/1.0/message',
                "comment": "Hi. Are you listening?",
                "response_requested": True
            })
            await transport_for_a.send(msg)
            resp = await transport_for_b.get_one()
            assert resp['message']['@id'] == msg['@id']
        print('\n>STOP')
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        print(f'>timeout: {delta.seconds}')
    finally:
        await agent1.close()
        await agent2.close()
