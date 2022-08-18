import asyncio
import queue
import threading
from typing import Optional, Coroutine


class BackgroundScheduler:

    __thread_singleton: Optional[threading.Thread] = None
    __thread_queue: Optional[queue.Queue] = None
    __thread_event_loop: Optional[asyncio.AbstractEventLoop] = None
    __lock_singleton = threading.Lock()

    @classmethod
    def schedule(cls, coro: Coroutine, task_hash: str = None):
        event_loop = cls.__get_event_loop()
        coro_broker = cls.__schedule_coroutine(coro, task_hash)
        asyncio.run_coroutine_threadsafe(coro_broker, loop=event_loop)

    @classmethod
    def unschedule(cls, task_hash: str):
        event_loop = cls.__get_event_loop()
        coro_broker = cls.__unschedule_coroutine(task_hash)
        asyncio.run_coroutine_threadsafe(coro_broker, loop=event_loop)

    @classmethod
    def __thread_routine(cls):
        asyncio.set_event_loop(cls.__thread_event_loop)
        asyncio.get_event_loop().run_forever()

    @classmethod
    def __get_event_loop(cls) -> asyncio.AbstractEventLoop:
        cls.__lock_singleton.acquire(blocking=True)
        try:
            if cls.__thread_queue is None:
                cls.__thread_queue = queue.Queue()
            if cls.__thread_event_loop is None:
                cls.__thread_event_loop = asyncio.new_event_loop()
            if cls.__thread_singleton is not None and not cls.__thread_singleton.is_alive():
                cls.__thread_singleton = None
            if cls.__thread_singleton is None:
                cls.__thread_singleton = threading.Thread(target=cls.__thread_routine)
                cls.__thread_singleton.daemon = True
                cls.__thread_singleton.start()
            return cls.__thread_event_loop
        finally:
            cls.__lock_singleton.release()

    @classmethod
    async def __schedule_coroutine(cls, coro: Coroutine, task_hash: str = None):
        if task_hash is None:
            tasks = []
        else:
            tasks_with_hash = [task for task in asyncio.all_tasks(cls.__thread_event_loop) if not task.done() and hasattr(task, 'hash')]
            tasks = [task for task in tasks_with_hash if task.hash == task_hash]
        if tasks:
            tsk = tasks[0]
            tsk.counter += 1
        else:
            tsk = asyncio.create_task(coro)
            tsk.hash = task_hash
            tsk.counter = 1

    @classmethod
    async def __unschedule_coroutine(cls, task_hash: str):
        tasks_with_hash = [task for task in asyncio.all_tasks(cls.__thread_event_loop) if not task.done() and hasattr(task, 'hash')]
        tasks = [task for task in tasks_with_hash if task.hash == task_hash]
        if tasks:
            tsk = tasks[0]
            tsk.counter -= 1
            if tsk.counter < 1:
                tsk.cancel()
