import uuid
from datetime import datetime

import pytest

from sirius_sdk import Agent
from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.messaging import Message
from sirius_sdk.agent.coprotocols import AbstractCoProtocolTransport
from .conftest import get_pairwise
from .helpers import run_coroutines


TEST_ITERATIONS = 100


async def routine_for_pinger(agent: Agent, p: Pairwise, thread_id: str):
    transport = await agent.spawn(thread_id, p)
    await transport.start()
    try:
        for n in range(TEST_ITERATIONS):
            ping = Message({
                '@id': 'message-id-' + uuid.uuid4().hex,
                '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test/1.0/ping',
                "comment": "Hi",
            })
            ok, pong = await transport.switch(ping)
            assert ok
            assert pong['@id'] == ping['@id']
    finally:
        await transport.stop()


@pytest.mark.asyncio
async def test_wallet_access(agent1: Agent, agent2: Agent):
    await agent1.open()
    await agent2.open()
    try:
        a2b = await get_pairwise(agent1, agent2)
        print('\n>START')
        stamp1 = datetime.now()
        for n in range(TEST_ITERATIONS):
            pw = await agent1.wallet.pairwise.get_pairwise(a2b.their.did)
        print('\n>STOP')
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        print(f'>timeout: {delta.seconds}')
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_decode_message(agent1: Agent):
    await agent1.open()
    try:
        seed = '000000000000000000000000000SEED1'
        packed = b'{"protected": "eyJlbmMiOiAieGNoYWNoYTIwcG9seTEzMDVfaWV0ZiIsICJ0eXAiOiAiSldNLzEuMCIsICJhbGciOiAiQXV0aGNyeXB0IiwgInJlY2lwaWVudHMiOiBbeyJlbmNyeXB0ZWRfa2V5IjogInBKcW1xQS1IVWR6WTNWcFFTb2dySGx4WTgyRnc3Tl84YTFCSmtHU2VMT014VUlwT0RQWTZsMVVsaVVvOXFwS0giLCAiaGVhZGVyIjogeyJraWQiOiAiM1ZxZ2ZUcDZRNFZlRjhLWTdlVHVXRFZBWmFmRDJrVmNpb0R2NzZLR0xtZ0QiLCAic2VuZGVyIjogIjRlYzhBeFRHcWtxamd5NHlVdDF2a0poeWlYZlNUUHo1bTRKQjk1cGZSMG1JVW9KajAwWmswNmUyUEVDdUxJYmRDck8xeTM5LUhGTG5NdW5YQVJZWk5rZ2pyYV8wYTBQODJpbVdNcWNHc1FqaFd0QUhOcUw1OGNkUUYwYz0iLCAiaXYiOiAiVU1PM2o1ZHZwQnFMb2Rvd3V0c244WEMzTkVqSWJLb2oifX1dfQ==", "iv": "MchkHF2M-4hneeUJ", "ciphertext": "UgcdsV-0rIkP25eJuRSROOuqiTEXp4NToKjPMmqqtJs-Ih1b5t3EEbrrHxeSfPsHtlO6J4OqA1jc5uuD3aNssUyLug==", "tag": "sQD8qgJoTrRoyQKPeCSBlQ=="}'
        await agent1.wallet.did.create_and_store_my_did(seed=seed)
        print('\n>START')
        stamp1 = datetime.now()
        for n in range(TEST_ITERATIONS):
            unpacked = await agent1.wallet.crypto.unpack_message(packed)
        print('\n>STOP')
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        print(f'>timeout: {delta.seconds}')
    finally:
        await agent1.close()


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
            message, sender_vk, recip_vk = await transport_for_b.get_one()
            assert message['@id'] == msg['@id']
        print('\n>STOP')
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        print(f'>timeout: {delta.seconds}')
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_switch_via_transport_in_coros(agent1: Agent, agent2: Agent):
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

        async def __producer(t: AbstractCoProtocolTransport):
            for n in range(TEST_ITERATIONS // 2):
                msg = Message({
                    '@id': 'message-id-' + uuid.uuid4().hex,
                    '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test/1.0/message',
                    "comment": "RUN",
                    "response_requested": True
                })
                ok, resp = await t.switch(msg)
                assert ok is True
            msg = Message({
                '@id': 'message-id-' + uuid.uuid4().hex,
                '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test/1.0/message',
                "comment": "STOP",
                "response_requested": True
            })
            await t.send(msg)

        async def __consumer(t: AbstractCoProtocolTransport):
            message, sender_vk, recip_vk = await t.get_one()
            while True:
                ok, message = await t.switch(message)
                if message['comment'] == 'STOP':
                    return

        print('\n>START')
        stamp1 = datetime.now()
        producer = __producer(transport_for_a)
        consumer = __consumer(transport_for_b)
        await run_coroutines(producer, consumer, timeout=60)
        print('\n>STOP')
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        print(f'>timeout: {delta.seconds}')
    finally:
        await agent1.close()
        await agent2.close()


@pytest.mark.asyncio
async def test_send_message_via_transport_via_websocket(agent1: Agent, agent2: Agent):
    await agent1.open()
    await agent2.open()
    try:
        a2b = await get_pairwise(agent1, agent2)
        b2a = await get_pairwise(agent2, agent1)
        thread_id = 'thread-' + uuid.uuid4().hex
        a2b.their.endpoint = a2b.their.endpoint.replace('http://', 'ws://')
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
            message, sender_vk, recip_vk = await transport_for_b.get_one()
            assert message['@id'] == msg['@id']
        print('\n>STOP')
        stamp2 = datetime.now()
        delta = stamp2 - stamp1
        print(f'>timeout: {delta.seconds}')
    finally:
        await agent1.close()
        await agent2.close()
