import uuid
import asyncio

import pytest

from sirius_sdk import Agent
from sirius_sdk.messaging import Message, register_message_class
from .helpers import ServerTestSuite


@pytest.mark.asyncio
async def test_same_account(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent1')
    session1 = Agent(
        server_address=params['server_address'],
        credentials=params['credentials'],
        p2p=params['p2p'],
        timeout=30,
    )
    session2 = Agent(
        server_address=params['server_address'],
        credentials=params['credentials'],
        p2p=params['p2p'],
        timeout=30,
    )
    await session1.open()
    await session2.open()
    try:
        # check locking OK
        resources = [f'resource-{uuid.uuid4().hex}' for i in range(100)]
        ok, busy = await session1.acquire(resources=resources, lock_timeout=5)
        try:
            assert ok is True
            ok, busy = await session2.acquire(resources=resources, lock_timeout=1)
            assert ok is False
            assert set(busy) == set(resources)
        finally:
            await session1.release()
        # check session ok may lock after explicitly release
        ok, busy = await session2.acquire(resources=resources, lock_timeout=1)
        assert ok is True
        # Check after timeout
        resources = [f'resource-{uuid.uuid4().hex}' for i in range(100)]
        timeout = 5.0
        ok, _ = await session1.acquire(resources=resources, lock_timeout=timeout)
        assert ok is True
        ok, _ = await session2.acquire(resources=resources, lock_timeout=1.0)
        assert ok is False
        await asyncio.sleep(timeout + 1.0)
        ok, _ = await session2.acquire(resources=resources, lock_timeout=1.0)
        assert ok is True
    finally:
        await session1.close()
        await session2.close()


@pytest.mark.asyncio
async def test_lock_multiple_time(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent1')
    session1 = Agent(
        server_address=params['server_address'],
        credentials=params['credentials'],
        p2p=params['p2p'],
        timeout=5,
    )
    session2 = Agent(
        server_address=params['server_address'],
        credentials=params['credentials'],
        p2p=params['p2p'],
        timeout=5,
    )
    await session1.open()
    await session2.open()
    try:
        resources1 = [f'resource-{uuid.uuid4().hex}']
        timeout = 5.0
        ok, _ = await session1.acquire(resources=resources1, lock_timeout=timeout)
        assert ok is True

        resources2 = [f'resource-{uuid.uuid4().hex}']
        ok, _ = await session1.acquire(resources=resources2, lock_timeout=timeout)
        assert ok is True
        # session1 must unlock previously locked resources on new acquire call
        ok, _ = await session2.acquire(resources=resources1, lock_timeout=timeout)
        assert ok is True
    finally:
        await session1.close()
        await session2.close()


@pytest.mark.asyncio
async def test_different_accounts(test_suite: ServerTestSuite):
    params1 = test_suite.get_agent_params('agent1')
    params2 = test_suite.get_agent_params('agent2')
    agent1 = Agent(
        server_address=params1['server_address'],
        credentials=params1['credentials'],
        p2p=params1['p2p'],
        timeout=5,
    )
    agent2 = Agent(
        server_address=params2['server_address'],
        credentials=params2['credentials'],
        p2p=params2['p2p'],
        timeout=5,
    )
    await agent1.open()
    await agent2.open()
    try:
        same_resources = [f'resource/{uuid.uuid4().hex}']

        ok1, _ = await agent1.acquire(resources=same_resources, lock_timeout=10.0)
        ok2, _ = await agent1.acquire(resources=same_resources, lock_timeout=10.0)

        assert ok1 is True
        assert ok2 is True
    finally:
        await agent1.close()
        await agent2.close()
