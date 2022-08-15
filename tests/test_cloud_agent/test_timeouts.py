import datetime
import json
import uuid

import pytest

import sirius_sdk
from sirius_sdk import Agent
from sirius_sdk.base import WebSocketConnector, Message
from sirius_sdk.errors.exceptions import SiriusTimeoutIO
from tests.helpers import ServerTestSuite
from tests.conftest import get_pairwise


@pytest.mark.asyncio
async def test_agent_rcv_timeout(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent4')
    timeout = 3
    # Check-1: check timeout error if ttl limit was set globally
    conn_with_global_setting = WebSocketConnector(
        server_address=params['server_address'],
        path='/rpc',
        credentials=params['credentials'],
        timeout=timeout,
    )
    await conn_with_global_setting.open()
    try:
        context = await conn_with_global_setting.read()
        assert context
        with pytest.raises(SiriusTimeoutIO):
            await conn_with_global_setting.read()
    finally:
        await conn_with_global_setting.close()

    # Check-2: check timeout error if ttl limit was set locally
    conn_with_local_setting = WebSocketConnector(
        server_address=params['server_address'],
        path='/rpc',
        credentials=params['credentials'],
        timeout=10000,  # infinite
    )
    await conn_with_local_setting.open()
    try:
        context = await conn_with_local_setting.read()
        assert context
        with pytest.raises(SiriusTimeoutIO):
            await conn_with_local_setting.read(timeout)
    finally:
        await conn_with_local_setting.close()

    # Check-3: check timeout for ttl was set greater than global setting
    conn_with_little_global_timeout = WebSocketConnector(
        server_address=params['server_address'],
        path='/rpc',
        credentials=params['credentials'],
        timeout=1,  # low value
    )
    await conn_with_little_global_timeout.open()
    try:
        context = await conn_with_little_global_timeout.read()
        assert context
        stamp1 = datetime.datetime.utcnow()
        with pytest.raises(SiriusTimeoutIO):
            await conn_with_little_global_timeout.read(timeout=5)
        stamp2 = datetime.datetime.utcnow()
        stamps_delta = stamp2 - stamp1
        assert 4 <= stamps_delta.total_seconds() <= 6, f'Timeout {stamps_delta.total_seconds()}'
    finally:
        await conn_with_little_global_timeout.close()


@pytest.mark.skip
@pytest.mark.asyncio
async def test_state_machines_timeout(test_suite: ServerTestSuite):
    params_me = test_suite.get_agent_params('agent4')
    params_their = test_suite.get_agent_params('agent3')
    timeout = 5
    me = Agent(
        server_address=params_me['server_address'],
        credentials=params_me['credentials'],
        p2p=params_me['p2p'],
        timeout=1000,
        name='agent4'
    )
    their = Agent(
        server_address=params_their['server_address'],
        credentials=params_their['credentials'],
        p2p=params_their['p2p'],
        timeout=timeout,
        name='agent3'
    )
    await me.open()
    await their.open()
    try:
        p2p = await get_pairwise(me, their)
        their_conn_key = await their.wallet.crypto.create_key()
        their_endpoint = [e for e in their.endpoints if e.routing_keys == []][0]
    finally:
        await me.close()
        await their.close()

    stamp1 = datetime.datetime.utcnow()
    async with sirius_sdk.context(params_me['server_address'], params_me['credentials'], params_me['p2p']):
        endpoints = await sirius_sdk.endpoints()
        endpoint = [e for e in endpoints if e.routing_keys == []][0]
        rfc_0160 = sirius_sdk.aries_rfc.Invitee(me=p2p.me, my_endpoint=endpoint, time_to_live=timeout)
        success, p2p = await rfc_0160.create_connection(
            invitation=sirius_sdk.aries_rfc.Invitation(
                label='Their', recipient_keys=[their_conn_key], endpoint=their_endpoint.address
            ),
            my_label='Me'
        )
        assert success is False
        assert rfc_0160.problem_report is not None
    stamp2 = datetime.datetime.utcnow()
    stamps_delta = stamp2 - stamp1
    assert 4 <= stamps_delta.total_seconds() <= 6, f'Timeout {stamps_delta.total_seconds()}'


@pytest.mark.asyncio
async def test_echo_big_message(agent4: Agent):
    await agent4.open()
    try:
        lst = [str(x) for x in range(100000)]
        big_data = ''.join(lst)
        stamp1 = datetime.datetime.utcnow()
        ret = await agent4.echo(message=big_data)
        stamp2 = datetime.datetime.utcnow()
        stamps_delta = stamp2 - stamp1
        stamps_delta_sec = stamps_delta.total_seconds()
        assert stamps_delta_sec < 1, f'Timeout {stamps_delta.total_seconds()}'
    finally:
        await agent4.close()
