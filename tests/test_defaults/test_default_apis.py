import asyncio
import os
import uuid
from os.path import isfile
from urllib.parse import urlparse

import pytest

import sirius_sdk
from sirius_sdk.messaging import Message
from sirius_sdk.hub.defaults.default_apis import APIDefault

from tests.helpers import ServerTestSuite, run_coroutines


@pytest.mark.asyncio
async def test_qr_codes():
    api = APIDefault()
    content = 'some-content/'*10
    url = await api.generate_qr_code(content)
    p = urlparse(url)
    paths = [p.path] + [p.path[1:]]
    assert any([isfile(path) for path in paths])
    # Clean
    for path in paths:
        if isfile(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_send(test_suite: ServerTestSuite):
    sender_params = test_suite.get_agent_params('agent1')
    receiver_params = test_suite.get_agent_params('agent2')
    sender_verkey = list(sender_params['entities'].items())[0][1]['verkey']
    receiver_verkey = list(receiver_params['entities'].items())[0][1]['verkey']

    async with sirius_sdk.context(**receiver_params):
        # Get receiver endpoint
        receiver_endpoints = await sirius_sdk.endpoints()
        listener = await sirius_sdk.subscribe()

        for vk_to_send in [sender_verkey, None]:
            for vk_to_receive in [receiver_verkey, None]:
                for endpoint in receiver_endpoints:

                    thread_id = uuid.uuid4().hex
                    msg_under_test = sirius_sdk.messaging.Message({
                        '@id': 'trust-ping-message-' + uuid.uuid4().hex,
                        '@type': 'https://didcomm.org/trust_ping/1.0/ping',
                        "comment": "Hi.",
                        '~thread': {"thid": thread_id}
                    })

                    # Allocate DefaultApi than configured for sender side
                    async with sirius_sdk.context(**sender_params):
                        api = APIDefault(crypto=sirius_sdk.Crypto)
                        await api.send(
                            message=msg_under_test, their_vk=vk_to_receive,
                            endpoint=endpoint.address, my_vk=vk_to_send, routing_keys=endpoint.routing_keys
                        )
                    # Pull events and check them
                    if vk_to_receive is None:
                        vk_to_send = None
                    event = await listener.get_one()
                    assert event.message == msg_under_test, f'Error for sender-vk: {vk_to_send}, routing_keys: {endpoint.routing_keys}'
                    assert event.sender_verkey == vk_to_send
                    assert event.recipient_verkey == vk_to_receive


@pytest.mark.asyncio
async def test_send_batched(test_suite: ServerTestSuite):
    sender_params = test_suite.get_agent_params('agent1')
    receiver1_params = test_suite.get_agent_params('agent2')
    receiver2_params = test_suite.get_agent_params('agent2')
    sender_verkey = list(sender_params['entities'].items())[0][1]['verkey']
    receiver1_verkey = list(receiver1_params['entities'].items())[0][1]['verkey']
    receiver2_verkey = list(receiver2_params['entities'].items())[0][1]['verkey']

    async with sirius_sdk.context(**receiver1_params):
        # Get receiver-1 default endpoint without routing keys
        endpoints = await sirius_sdk.endpoints()
        receiver1_endpoint = [e for e in endpoints if e.routing_keys == []][0]
    async with sirius_sdk.context(**receiver2_params):
        # Get receiver-1 default endpoint without routing keys
        endpoints = await sirius_sdk.endpoints()
        receiver2_endpoint = [e for e in endpoints if e.routing_keys == []][0]

    async def pull_first_event(**sdk):
        async with sirius_sdk.context(**sdk):
            listener = await sirius_sdk.subscribe()
            event = await listener.get_one(timeout=15)
            return event

    listener1_fut = asyncio.ensure_future(pull_first_event(**receiver1_params))
    listener2_fut = asyncio.ensure_future(pull_first_event(**receiver2_params))

    msg_under_test = sirius_sdk.messaging.Message({
        '@id': 'trust-ping-message-' + uuid.uuid4().hex,
        '@type': 'https://didcomm.org/trust_ping/1.0/ping',
        "comment": "Hi.",
        '~thread': {"thid": uuid.uuid4().hex}
    })

    async with sirius_sdk.context(**sender_params):
        api = APIDefault(crypto=sirius_sdk.Crypto)
        batches = [
            sirius_sdk.RoutingBatch(
                their_vk=receiver1_verkey,
                endpoint=receiver1_endpoint.address,
                my_vk=sender_verkey,
                routing_keys=receiver1_endpoint.routing_keys
            ),
            sirius_sdk.RoutingBatch(
                their_vk=receiver2_verkey,
                endpoint=receiver2_endpoint.address,
                my_vk=sender_verkey,
                routing_keys=receiver2_endpoint.routing_keys
            )
        ]
        sender_results = await api.send_batched(message=msg_under_test, batches=batches)
        assert len(sender_results) == 2
        for success, body in sender_results:
            assert success is True
            assert isinstance(body, str)

        listeners_results = await run_coroutines(listener1_fut, listener2_fut)
        assert all([event.message == msg_under_test for event in listeners_results])