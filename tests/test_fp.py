import asyncio

import pytest

import sirius_sdk.errors.indy_exceptions as indy_exceptions
from sirius_sdk.rpc.fp import Future
from sirius_sdk.errors.exceptions import *


@pytest.mark.asyncio
async def test_sane():
    future = Future()
    promise = future.promise
    with pytest.raises(SiriusPendingOperation):
        future.get_value()
    assert promise.is_triggered is False
    ok = await future.wait(1)
    assert ok is False
    promise.set_value('Hello')
    ok = await future.wait(1)
    assert ok is True
    value = future.get_value()
    assert value == 'Hello'
    assert promise.is_triggered is True
    with pytest.raises(SiriusAlreadyTriggered):
        await promise.set_value('Hello')


@pytest.mark.asyncio
async def test_set_non_indy_error():

    class SpecificError(Exception):
        pass

    future = Future()
    promise = future.promise
    exc = SpecificError('test error message')
    promise.set_exception(exc)
    ok = await future.wait(3)
    assert ok is True

    has_exc = future.has_exception()
    assert has_exc is True

    fut_exc = None
    try:
        future.raise_exception()
    except SpecificError as exc:
        fut_exc = exc

    assert fut_exc is not None
    assert str(fut_exc) == 'test error message'


@pytest.mark.asyncio
async def test_set_indy_error():
    future = Future()
    promise = future.promise

    exc = indy_exceptions.WalletItemNotFound(
        error_code=indy_exceptions.ErrorCode.WalletItemNotFound,
        error_details=dict(message='test error message', indy_backtrace='')
    )
    promise.set_exception(exc)
    ok = await future.wait(3)
    assert ok is True

    has_exc = future.has_exception()
    assert has_exc is True

    fut_exc = None
    try:
        future.raise_exception()
    except indy_exceptions.WalletItemNotFound as exc:
        fut_exc = exc

    assert fut_exc is not None
    assert isinstance(fut_exc, indy_exceptions.WalletItemNotFound)
    assert fut_exc.message == 'test error message'


@pytest.mark.asyncio
async def test_tuple_value():
    future = Future()
    promise = future.promise

    expected = (1, 2, 'value')
    promise.set_value(expected)

    ok = await future.wait(3)
    assert ok is True
    actual = future.get_value()
    assert expected == actual


@pytest.mark.asyncio
async def test_bytes_value():
    future = Future()
    promise = future.promise

    expected = b'Hello Test!'
    promise.set_value(expected)

    ok = await future.wait(3)
    assert ok is True
    actual = future.get_value()
    assert expected == actual
