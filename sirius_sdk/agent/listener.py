import sys
import asyncio

from sirius_sdk.agent.connections import AgentEvents
from sirius_sdk.errors.exceptions import SiriusConnectionClosed
from sirius_sdk.messaging import Message, restore_message_instance


PY_35 = sys.version_info >= (3, 5)
PY_352 = sys.version_info >= (3, 5, 2)


class Listener:

    def __init__(self, source: AgentEvents):
        self.__source = source

    async def get_one(self, timeout: int=None) -> Message:
        event = await self.__source.pull(timeout)
        if 'message' in event:
            ok, message = restore_message_instance(event['message'])
            if ok:
                event['message'] = message
            else:
                event['message'] = Message(event['message'])
        return event

    if PY_35:
        def __aiter__(self):
            if not self.__source.is_open:
                raise SiriusConnectionClosed()
            return self

        # Old 3.5 versions require a coroutine
        if not PY_352:
            __aiter__ = asyncio.coroutine(__aiter__)

        @asyncio.coroutine
        def __anext__(self):
            """Asyncio iterator interface for listener

            Note:
                TopicAuthorizationFailedError and OffsetOutOfRangeError
                exceptions can be raised in iterator.
                All other KafkaError exceptions will be logged and not raised
            """
            while True:
                return (yield from self.get_one())