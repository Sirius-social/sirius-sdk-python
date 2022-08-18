import asyncio
import uuid

import pytest

from sirius_sdk.hub.backgrounds import BackgroundScheduler


@pytest.mark.asyncio
async def test_sane_for_empty_task_hash():

    work_count = 5
    queue1 = asyncio.Queue(maxsize=work_count)
    queue2 = asyncio.Queue(maxsize=work_count)

    async def __task1__():
        for n in range(work_count):
            queue1.put_nowait(n)

    async def __task2__():
        for n in range(work_count):
            queue2.put_nowait(n)

    # Check for empty task_hash
    BackgroundScheduler.schedule(coro=__task1__(), task_hash=None)
    BackgroundScheduler.schedule(coro=__task2__(), task_hash=None)
    await asyncio.wait([queue1.join(), queue2.join()], timeout=5)


@pytest.mark.asyncio
async def test_sane_for_filled_task_hash():

    work_count = 5
    queue1 = asyncio.Queue()
    queue2 = asyncio.Queue()
    task_hash = 'Hash-Value-' + uuid.uuid4().hex

    async def __task1__():
        for n in range(work_count):
            await asyncio.sleep(0.1)
            queue1.put_nowait(n+10)

    async def __task2__():
        for n in range(work_count):
            await asyncio.sleep(0.1)
            queue2.put_nowait(n+30)

    # Check for empty task_hash
    BackgroundScheduler.schedule(coro=__task1__(), task_hash=task_hash)
    BackgroundScheduler.schedule(coro=__task2__(), task_hash=task_hash)
    await asyncio.sleep(3)
    assert queue1.empty() is False and queue1.qsize() == work_count
    assert queue2.empty() is True


@pytest.mark.asyncio
async def test_unschedule():

    task_queue = asyncio.Queue()
    task_hash = 'Hash-Value-' + uuid.uuid4().hex

    async def __task__():
        while True:
            await asyncio.sleep(0.1)
            task_queue.put_nowait(None)

    BackgroundScheduler.schedule(coro=__task__(), task_hash=task_hash)
    BackgroundScheduler.schedule(coro=__task__(), task_hash=task_hash)
    await asyncio.sleep(1)
    count1 = task_queue.qsize()
    assert count1 > 0

    BackgroundScheduler.unschedule(task_hash=task_hash)
    await asyncio.sleep(1)
    count2 = task_queue.qsize()
    assert count2 > count1

    BackgroundScheduler.unschedule(task_hash=task_hash)
    await asyncio.sleep(1)
    count3 = task_queue.qsize()
    assert count3 == count2

