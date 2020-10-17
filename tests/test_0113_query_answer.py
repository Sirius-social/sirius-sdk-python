import datetime

import pytest

import sirius_sdk
from sirius_sdk.agent.aries_rfc.feature_0113_question_answer import make_answer, ask_and_wait_answer

from .conftest import get_pairwise
from .helpers import ServerTestSuite, run_coroutines


@pytest.mark.asyncio
async def test_sane(agent1: sirius_sdk.Agent, agent2: sirius_sdk.Agent, test_suite: ServerTestSuite):

    requester = agent1
    responder = agent2
    await requester.open()
    await responder.open()
    try:
        req2resp = await get_pairwise(requester, responder)
    finally:
        await requester.close()
        await responder.close()

    params_req = test_suite.get_agent_params('agent1')
    params_resp = test_suite.get_agent_params('agent2')

    async def requester(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, *args, **kwargs):
        async with sirius_sdk.context(server_address, credentials, p2p):
            q = sirius_sdk.agent.Question(
                valid_responses=['Yes', 'No'],
                question_text='Test question',
                question_detail='Question detail'
            )
            q.set_ttl(30)
            success, answer = await ask_and_wait_answer(q, req2resp)
            return success and answer.response == 'Yes'

    async def responder(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, *args, **kwargs):
        async with sirius_sdk.context(server_address, credentials, p2p):
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                if isinstance(event.message, sirius_sdk.agent.Question):
                    await make_answer('Yes', event.message, event.pairwise)
                    return True

    coro_requester = requester(**params_req)
    coro_responder = responder(**params_resp)
    print('Run state machines')
    results = await run_coroutines(coro_requester, coro_responder, timeout=60)
    print('Finish state machines')
    print(str(results))
    assert len(results) == 2
    assert all(ret is True for ret in results)


@pytest.mark.asyncio
async def test_timeout(agent1: sirius_sdk.Agent, agent2: sirius_sdk.Agent, test_suite: ServerTestSuite):

    requester = agent1
    responder = agent2
    await requester.open()
    await responder.open()
    try:
        req2resp = await get_pairwise(requester, responder)
    finally:
        await requester.close()
        await responder.close()

    params_req = test_suite.get_agent_params('agent1')
    results = None
    timeout = 10

    async def requester(server_address: str, credentials: bytes, p2p: sirius_sdk.P2PConnection, *args, **kwargs):
        nonlocal results
        nonlocal timeout
        async with sirius_sdk.context(server_address, credentials, p2p):
            q = sirius_sdk.agent.Question(
                valid_responses=['Yes', 'No'],
                question_text='Test question',
                question_detail='Question detail'
            )
            q.set_ttl(timeout)
            results = await ask_and_wait_answer(q, req2resp)

    coro_requester = requester(**params_req)
    print('Run state machines')
    stamp1 = datetime.datetime.now()
    await run_coroutines(coro_requester, timeout=2*timeout)
    stamp2 = datetime.datetime.now()
    print('Finish state machines')
    print(str(results))
    assert isinstance(results, tuple)
    assert len(results) == 2
    success, message = results
    assert success is False
    assert message is None

    delta = stamp2 - stamp1
    secs = delta.total_seconds()
    assert 4/5*timeout < secs < 2*timeout
