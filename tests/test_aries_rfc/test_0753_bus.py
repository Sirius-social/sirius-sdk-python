import uuid

import pytest

from sirius_sdk.errors.exceptions import BaseSiriusException
from sirius_sdk import Agent, Pairwise
from sirius_sdk.messaging import restore_message_instance
from sirius_sdk.agent.aries_rfc.feature_0753_bus import *

from tests.helpers import run_coroutines, IndyAgent


@pytest.mark.asyncio
async def test_messages():
    cast1 = BusOperation.Cast(thid='some-thread-id')
    assert cast1.validate() is True
    cast2 = BusOperation.Cast(recipient_vk='VK1', sender_vk='VK2', protocols=['some-protocol'])
    assert cast2.validate() is True
    err_cast = BusOperation.Cast(recipient_vk='VK1', sender_vk='VK2')
    assert err_cast.validate() is False

    op_subscribe1 = BusSubscribeRequest(cast1)
    assert op_subscribe1.cast.thid == 'some-thread-id'
    assert op_subscribe1.cast.sender_vk is None and op_subscribe1.cast.recipient_vk is None
    assert op_subscribe1.thread_id is None

    op_subscribe2 = BusSubscribeRequest(cast2)
    assert op_subscribe2.cast.thid is None
    assert op_subscribe2.cast.sender_vk == 'VK2'
    assert op_subscribe2.cast.recipient_vk == 'VK1'

    bind = BusBindResponse(thread_id='some-bind-id')
    assert bind.thread_id == 'some-bind-id'
    assert bind.parent_thread_id is None

    ok, msg = restore_message_instance(
        {
            '@type': 'https://didcomm.org/bus/1.0/bind',
            '~thread': {'thid': 'some-binding-id2'}
        }
    )
    assert ok is True
    assert isinstance(msg, BusBindResponse)
    assert msg.thread_id == 'some-binding-id2'
    assert msg.parent_thread_id is None

    op_subscribe_client_id = BusSubscribeRequest(cast1, parent_thread_id='client-id')
    assert op_subscribe_client_id.parent_thread_id == 'client-id'
    op_bind_client_id = BusBindResponse(thread_id='some-bind-id', parent_thread_id='client-id')
    assert op_bind_client_id.parent_thread_id == 'client-id'
    op_unsubscr_client_id = BusUnsubscribeRequest(client_id='client-id', aborted=True)
    assert op_unsubscr_client_id.client_id == 'client-id'
    assert op_unsubscr_client_id.aborted is True
