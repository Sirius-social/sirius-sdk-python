import asyncio
from dataclasses import dataclass
from asyncio.queues import Queue as AsyncQueue
from typing import Dict
from threading import Lock

import sirius_sdk
from sirius_sdk.errors.exceptions import SiriusTimeoutIO, OperationAbortedManually
from sirius_sdk.abstract.api import *
from sirius_sdk.messaging import restore_message_instance
from sirius_sdk.abstract.bus import AbstractBus


@dataclass
class Event:
    topic: str
    payload: bytes
    abort: bool = False


class Observer:

    def __init__(self, client_id: str, queue: AsyncQueue, loop: asyncio.AbstractEventLoop):
        self.__queue = queue
        self.__loop = loop
        self.__client_id = client_id

    @property
    def client_id(self) -> str:
        return self.__client_id

    def notify(self, event: Any):
        coro = self.__queue.put(event)
        # Thread-Safe!!!
        asyncio.run_coroutine_threadsafe(coro, loop=self.__loop)


class Subscriptions:

    def __init__(self):
        self.__lock = Lock()
        # Map topic to observers-list
        self.__subscriptions_singleton: Dict[str, List[Observer]] = {}

    def subscribe(self, topic: str, o: Observer):
        self.__acquire()
        try:
            observers = self.__subscriptions_singleton.get(topic, [])
            if not list(filter(lambda x: x.client_id == o.client_id, observers)):
                observers.append(o)
                self.__subscriptions_singleton[topic] = observers
        finally:
            self.__release()

    def unsubscribe(self, client_id: str, topics: List[str] = None):
        self.__acquire()
        try:
            if topics is not None:
                topics_to_process = topics or []
            else:
                # unsubscribe all topics for specified client_id
                topics_to_process = []
                for topic in self.__subscriptions_singleton.keys():
                    observers = self.__subscriptions_singleton.get(topic, [])
                    if list(filter(lambda x: x.client_id == client_id, observers)):
                        topics_to_process.append(topic)
            # Process
            for topic in topics_to_process:
                observers = self.__subscriptions_singleton.get(topic, [])
                self.__subscriptions_singleton[topic] = [o for o in observers if o.client_id != client_id]
        finally:
            self.__release()

    def notify(self, topic: str, payload: bytes) -> int:
        self.__acquire()
        try:
            observers = self.__subscriptions_singleton.get(topic, [])
        finally:
            self.__release()
        # Notify all
        for o in observers:
            o.notify(event=Event(topic, payload))
        return len(observers)

    def notify_abort(self, client_id: str):
        o: Optional[Observer] = None
        self.__acquire()
        try:
            for topic in self.__subscriptions_singleton.keys():
                observers = self.__subscriptions_singleton.get(topic, [])
                found = list(filter(lambda x: x.client_id == client_id, observers))
                if found:
                    o = found[0]
                    break
        finally:
            self.__release()
        # Fire!!!
        if o is not None:
            o.notify(event=Event(topic='*', payload=b'', abort=True))

    def __acquire(self):
        self.__lock.acquire(blocking=True)

    def __release(self):
        self.__lock.release()


class InMemoryBus(AbstractBus):

    __subscriptions_singleton = Subscriptions()

    def __init__(self, crypto: APICrypto = None, loop: asyncio.AbstractEventLoop = None):
        self.__crypto = crypto or sirius_sdk.Crypto
        self.__queue = AsyncQueue()
        self.__client_id = str(id(self))
        if loop is None:
            loop = asyncio.get_event_loop()
        self.__observer = Observer(client_id=self.__client_id, queue=self.__queue, loop=loop)

    async def subscribe(self, thid: str) -> bool:
        self.__subscriptions_singleton.subscribe(thid, self.__observer)
        return True

    async def subscribe_ext(
            self, sender_vk: List[str], recipient_vk: List[str], protocols: List[str]
    ) -> (bool, List[str]):
        raise NotImplemented

    async def unsubscribe(self, thid: str):
        self.__subscriptions_singleton.unsubscribe(client_id=self.__client_id, topics=[thid])

    async def unsubscribe_ext(self, thids: List[str]):
        self.__subscriptions_singleton.unsubscribe(client_id=self.__client_id, topics=thids)

    async def publish(self, thid: str, payload: bytes) -> int:
        num = self.__subscriptions_singleton.notify(thid, payload)
        return num

    async def get_event(self, timeout: float = None) -> AbstractBus.BytesEvent:
        if timeout is None:
            event: Event = await self.__queue.get()
        else:
            coro = self.__queue.get()
            done, pending = await asyncio.wait([coro], timeout=timeout)
            if done:
                event: Event = list(done)[0].result()
            else:
                raise SiriusTimeoutIO
        #
        if event.abort:
            raise OperationAbortedManually
        else:
            return AbstractBus.BytesEvent(thread_id=event.topic, payload=event.payload)

    async def get_message(self, timeout: float = None) -> AbstractBus.MessageEvent:
        event = await self.get_event(timeout)
        decrypted = await self.__crypto.unpack_message(event.payload)
        ok, msg = restore_message_instance(decrypted['message'])
        if not ok:
            msg = Message(**decrypted['message'])
        return AbstractBus.MessageEvent(
            thread_id=event.thread_id,
            message=msg,
            sender_verkey=decrypted.get('sender_verkey', None),
            recipient_verkey=decrypted.get('recipient_verkey', None)
        )

    async def abort(self):
        self.__subscriptions_singleton.notify_abort(self.__client_id)
