import base64
import datetime

import pytest

from sirius_sdk.messaging import Message
from sirius_sdk.rpc import Future
from sirius_sdk.rpc.futures import MSG_TYPE as MSG_TYPE_FUTURE
from sirius_sdk.errors.exceptions import *
from sirius_sdk.errors.indy_exceptions import WalletItemAlreadyExists, ErrorCode


@pytest.mark.asyncio
async def test_sane(p2p: dict):
    agent_to_sdk = p2p['agent']['tunnel']
    sdk_to_agent = p2p['sdk']['tunnel']

    future = Future(tunnel=sdk_to_agent)

    with pytest.raises(SiriusPendingOperation):
        future.get_value()

    expected = 'Test OK'
    promise_msg = Message({
        '@type': MSG_TYPE_FUTURE,
        '@id': 'promise-message-id',
        'is_tuple': False,
        'is_bytes': False,
        'value': expected,
        'exception': None,
        '~thread': {
            'thid': future.promise['id']
        }
    })

    ok = await future.wait(5)
    assert ok is False

    await agent_to_sdk.post(message=promise_msg)
    ok = await future.wait(5)
    assert ok is True

    actual = future.get_value()
    assert actual == expected


@pytest.mark.asyncio
async def test_set_non_indy_error(p2p: dict):
    agent_to_sdk = p2p['agent']['tunnel']
    sdk_to_agent = p2p['sdk']['tunnel']

    future = Future(tunnel=sdk_to_agent)

    exc = RuntimeError('test error message')

    promise_msg = Message({
        '@type': MSG_TYPE_FUTURE,
        '@id': 'promise-message-id',
        'is_tuple': False,
        'is_bytes': False,
        'value': None,
        'exception': {
            'indy': None,
            'class_name': exc.__class__.__name__,
            'printable': str(exc)
        },
        '~thread': {
            'thid': future.promise['id']
        }
    })

    await agent_to_sdk.post(message=promise_msg)
    ok = await future.wait(5)
    assert ok is True

    has_exc = future.has_exception()
    assert has_exc is True

    fut_exc = None
    try:
        future.raise_exception()
    except SiriusPromiseContextException as exc:
        fut_exc = exc

    assert fut_exc is not None
    assert isinstance(fut_exc, SiriusPromiseContextException)
    assert fut_exc.printable == 'test error message'
    assert fut_exc.class_name == 'RuntimeError'


@pytest.mark.asyncio
async def test_set_indy_error(p2p: dict):
    agent_to_sdk = p2p['agent']['tunnel']
    sdk_to_agent = p2p['sdk']['tunnel']

    future = Future(tunnel=sdk_to_agent)

    exc = WalletItemAlreadyExists(
        error_code=ErrorCode.WalletItemAlreadyExists,
        error_details=dict(message='test error message', indy_backtrace='')
    )

    promise_msg = Message({
        '@type': MSG_TYPE_FUTURE,
        '@id': 'promise-message-id',
        'is_tuple': False,
        'is_bytes': False,
        'value': None,
        'exception': {
            'indy': {
                'error_code': exc.error_code,
                'message': exc.message
            },
            'class_name': exc.__class__.__name__,
            'printable': str(exc)
        },
        '~thread': {
            'thid': future.promise['id']
        }
    })

    await agent_to_sdk.post(message=promise_msg)
    ok = await future.wait(5)
    assert ok is True

    has_exc = future.has_exception()
    assert has_exc is True

    fut_exc = None
    try:
        future.raise_exception()
    except WalletItemAlreadyExists as exc:
        fut_exc = exc

    assert fut_exc is not None
    assert isinstance(fut_exc, WalletItemAlreadyExists)
    assert fut_exc.message == 'test error message'


@pytest.mark.asyncio
async def test_tuple_value(p2p: dict):
    agent_to_sdk = p2p['agent']['tunnel']
    sdk_to_agent = p2p['sdk']['tunnel']

    future = Future(tunnel=sdk_to_agent)

    expected = (1, 2, 'value')
    promise_msg = Message({
        '@type': MSG_TYPE_FUTURE,
        '@id': 'promise-message-id',
        'is_tuple': True,
        'is_bytes': False,
        'value': expected,
        'exception': None,
        '~thread': {
            'thid': future.promise['id']
        }
    })

    await agent_to_sdk.post(message=promise_msg)
    ok = await future.wait(3)
    assert ok is True
    actual = future.get_value()
    assert expected == actual


@pytest.mark.asyncio
async def test_bytes_value(p2p: dict):
    agent_to_sdk = p2p['agent']['tunnel']
    sdk_to_agent = p2p['sdk']['tunnel']

    future = Future(tunnel=sdk_to_agent)

    expected = b'Hello!'
    promise_msg = Message({
        '@type': MSG_TYPE_FUTURE,
        '@id': 'promise-message-id',
        'is_tuple': False,
        'is_bytes': True,
        'value': base64.b64encode(expected).decode('ascii'),
        'exception': None,
        '~thread': {
            'thid': future.promise['id']
        }
    })

    await agent_to_sdk.post(message=promise_msg)
    ok = await future.wait(3)
    assert ok is True
    actual = future.get_value()
    assert expected == actual
