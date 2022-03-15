import sys
import asyncio
from typing import Optional, List, Generator

from sirius_sdk.agent.connections import AgentEvents
from sirius_sdk.errors.exceptions import SiriusConnectionClosed
from sirius_sdk.messaging import Message, restore_message_instance
from sirius_sdk.agent.pairwise import AbstractPairwiseList, Pairwise


PY_35 = sys.version_info >= (3, 5)
PY_352 = sys.version_info >= (3, 5, 2)


class Event(Message):
    
    def __init__(self, pairwise: Pairwise = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__pairwise = pairwise

    @property
    def pairwise(self) -> Pairwise:
        return self.__pairwise

    @property
    def message(self) -> Optional[Message]:
        if 'message' in self:
            return self['message']
        else:
            return None

    @property
    def recipient_verkey(self) -> Optional[str]:
        return self.get('recipient_verkey', None)

    @property
    def sender_verkey(self) -> Optional[str]:
        return self.get('sender_verkey', None)

    @property
    def forwarded_keys(self) -> List[str]:
        return self.get('forwarded_keys', [])

    @property
    def content_type(self) -> Optional[str]:
        return self.get('content_type', None)

    @property
    def extra(self) -> Optional[dict]:
        return self.get('~extra', None)


class Listener:

    def __init__(self, source: AgentEvents, pairwise_resolver: AbstractPairwiseList = None):
        self.__source = source
        self.__pairwise_resolver = pairwise_resolver

    async def get_one(self, timeout: int = None) -> Event:
        event = await self.__source.pull(timeout)
        if 'message' in event:
            ok, message = restore_message_instance(event['message'])
            if ok:
                event['message'] = message
            else:
                event['message'] = Message(event['message'])
        their_verkey = event.get('sender_verkey', None)
        if self.__pairwise_resolver and their_verkey:
            pairwise = await self.__pairwise_resolver.load_for_verkey(their_verkey)
        else:
            pairwise = None
        return Event(pairwise=pairwise, **event)

    def __aiter__(self) -> Generator[Event, None, None]:
        if not self.__source.is_open:
            raise SiriusConnectionClosed()
        return self

    async def __anext__(self):
        while True:
            e = await self.get_one()
            return e
