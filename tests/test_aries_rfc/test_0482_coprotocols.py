import uuid

import pytest

import sirius_sdk
from sirius_sdk import Agent
from sirius_sdk.agent.aries_rfc.feature_0482_coprotocol import Caller, Called

from tests.conftest import get_pairwise
from tests.helpers import ServerTestSuite, run_coroutines
from sirius_sdk.agent.aries_rfc.feature_0482_coprotocol.messages import *
from sirius_sdk.recipes import as_caller, as_called


@pytest.mark.asyncio
async def test_invoke(A: Agent, B: Agent, test_suite: ServerTestSuite):
    caller = A
    called = B
    caller_params = test_suite.get_agent_params('agent1')
    called_params = test_suite.get_agent_params('agent2')
    await caller.open()
    await called.open()
    try:
        caller_2_called = await get_pairwise(caller, called)
        test_log = {}

        async def run_caller():
            uri, cred, p2p = caller_params['server_address'], caller_params['credentials'], caller_params['p2p']
            cfg = sirius_sdk.Config().setup_cloud(uri, cred, p2p)
            async with sirius_sdk.context(cfg):
                machine = Caller(called=caller_2_called, thid=uuid.uuid4().hex)
                assert machine.state == Caller.State.NULL
                success, ctx = await machine.bind(
                    cast=[
                        {'role': 'payer', 'id': None},
                        {'role': 'provider', 'id': caller_2_called.their.did}
                    ]
                )
                assert machine.state == Caller.State.ATTACHED
                test_log['caller_attached'] = (success, dict(**ctx))
                await machine.input(data={'key': 'value'}, extra_key='extra-value')
                success, data, extra = await machine.wait_output()
                test_log['caller_output_1'] = (success, dict(**data), dict(**extra))
                await machine.detach()
                assert machine.state == Caller.State.DETACHED
                test_log['caller_done'] = True

        async def run_called():
            uri, cred, p2p = called_params['server_address'], called_params['credentials'], called_params['p2p']
            cfg = sirius_sdk.Config().setup_cloud(uri, cred, p2p)
            async with sirius_sdk.context(cfg):
                listener = await sirius_sdk.subscribe()
                async for event in listener:
                    request = event.message
                    if isinstance(request, CoProtocolBind):
                        machine = await Called.open(caller=event.pairwise, request=request)
                        assert machine.state == Called.State.NULL
                        test_log['called_bind_context'] = dict(**machine.context)
                        assert machine.state == Called.State.NULL
                        await machine.attach(field1='value-1', field2='value-2')
                        assert machine.state == Called.State.ATTACHED
                        success, data, extra = await machine.wait_input()
                        test_log['called_input_1'] = (success, dict(**data), dict(**extra))
                        await machine.output(data={'key': 'value-from-called'}, extra_key='extra-value-from-called')
                        try:
                            await machine.wait_input()
                        except Called.CoProtocolDetachedByCaller as e:
                            test_log['called_input_exception'] = str(e)
                        assert machine.state == Called.State.DONE
                        test_log['called_done'] = True
                        return
        print('> begin')
        await run_coroutines(run_caller(), run_called(), timeout=5)
        print('> end')
        assert test_log.get('called_bind_context') == {'co_binding_id': None, 'cast': [{'role': 'payer', 'id': None}, {'role': 'provider', 'id': 'T8MtAB98aCkgNLtNfQx6WG'}]}
        assert test_log.get('caller_attached') == (True, {'field1': 'value-1', 'field2': 'value-2'})
        assert test_log.get('called_input_1') == (True, {'key': 'value'}, {'extra_key': 'extra-value'})
        assert test_log.get('caller_output_1') == (True, {'key': 'value-from-called'}, {'extra_key': 'extra-value-from-called'})
        assert test_log.get('called_input_exception') is not None
        assert test_log.get('called_done') is True
        assert test_log.get('caller_done') is True
    finally:
        await caller.close()
        await called.close()


@pytest.mark.asyncio
async def test_caller_problem_report(A: Agent, B: Agent, test_suite: ServerTestSuite):
    caller = A
    called = B
    caller_params = test_suite.get_agent_params('agent1')
    called_params = test_suite.get_agent_params('agent2')
    await caller.open()
    await called.open()
    try:
        caller_2_called = await get_pairwise(caller, called)
        test_log = {}

        async def run_caller():
            uri, cred, p2p = caller_params['server_address'], caller_params['credentials'], caller_params['p2p']
            cfg = sirius_sdk.Config().setup_cloud(uri, cred, p2p)
            async with sirius_sdk.context(cfg):
                machine = Caller(called=caller_2_called, thid=uuid.uuid4().hex)
                success, ctx = await machine.bind(
                    cast=[
                        {'role': 'payer', 'id': None},
                        {'role': 'provider', 'id': caller_2_called.their.did}
                    ]
                )
                assert success is True
                await machine.raise_problem(problem_code='123', explain='TEST')
                assert machine.state == Caller.State.ATTACHED
                test_log['caller_done'] = True

        async def run_called():
            uri, cred, p2p = called_params['server_address'], called_params['credentials'], called_params['p2p']
            cfg = sirius_sdk.Config().setup_cloud(uri, cred, p2p)
            async with sirius_sdk.context(cfg):
                listener = await sirius_sdk.subscribe()
                async for event in listener:
                    request = event.message
                    if isinstance(request, CoProtocolBind):
                        machine = await Called.open(caller=event.pairwise, request=request)
                        await machine.attach()
                        success, data, extra = await machine.wait_input()
                        test_log['called_input_1'] = success, data, extra
                        if success is False:
                            test_log['called_problem_report'] = (machine.problem_report.problem_code, machine.problem_report.explain)
                        assert machine.state == Called.State.ATTACHED
                        test_log['called_done'] = True
                        return
        print('> begin')
        await run_coroutines(run_caller(), run_called(), timeout=5)
        print('> end')
        assert test_log.get('called_input_1') == (False, None, None)
        assert test_log.get('called_problem_report') == ('123', 'TEST')
        assert test_log.get('called_done') is True
        assert test_log.get('caller_done') is True
    finally:
        await caller.close()
        await called.close()


@pytest.mark.asyncio
async def test_recipe_1(A: Agent, B: Agent, test_suite: ServerTestSuite):
    caller = A
    called = B
    caller_params = test_suite.get_agent_params('agent1')
    called_params = test_suite.get_agent_params('agent2')
    await caller.open()
    await called.open()
    try:
        caller_2_called = await get_pairwise(caller, called)
        test_log = {}

        async def run_caller():
            uri, cred, p2p = caller_params['server_address'], caller_params['credentials'], caller_params['p2p']
            cfg = sirius_sdk.Config().setup_cloud(uri, cred, p2p)
            async with sirius_sdk.context(cfg):
                async with as_caller(called=caller_2_called, thid=uuid.uuid4().hex, cast={'cast-key': 'cast-val'}) as proto:
                    assert proto.state == Caller.State.ATTACHED
                    test_log['caller_attached'] = True
                    await proto.input(data={'key': 'value'}, extra_key='extra-value')
                    success, data, extra = await proto.wait_output()
                    test_log['caller_output_1'] = (success, dict(**data), dict(**extra))
                    await proto.detach()
                    assert proto.state == Caller.State.DETACHED
                    test_log['caller_done'] = True

        async def run_called():
            uri, cred, p2p = called_params['server_address'], called_params['credentials'], called_params['p2p']
            cfg = sirius_sdk.Config().setup_cloud(uri, cred, p2p)
            async with sirius_sdk.context(cfg):
                listener = await sirius_sdk.subscribe()
                async for event in listener:
                    request = event.message
                    if isinstance(request, CoProtocolBind):
                        async with as_called(caller=event.pairwise, request=request) as proto:
                            await proto.attach()
                            success, data, extra = await proto.wait_input()
                            test_log['called_input_1'] = success, data, extra
                            await proto.output(data={'key': 'value-from-called'}, extra_key='extra-value-from-called')
                            try:
                                await proto.wait_input()
                            except Called.CoProtocolDetachedByCaller as e:
                                test_log['called_input_exception'] = str(e)
                            assert proto.state == Called.State.DONE
                            test_log['called_done'] = True
                            return
        print('> begin')
        await run_coroutines(run_caller(), run_called(), timeout=5)
        print('> end')
        for event in ['caller_attached', 'called_input_1', 'caller_output_1', 'called_input_exception', 'called_done', 'caller_done']:
            assert event in test_log.keys()
    finally:
        await caller.close()
        await called.close()

