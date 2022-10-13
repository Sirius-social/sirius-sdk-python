import sys
import asyncio
from typing import Optional, List, Generator

from sirius_sdk.abstract.listener import Event, AbstractListener
from sirius_sdk.agent.connections import AgentEvents
from sirius_sdk.errors.exceptions import SiriusConnectionClosed
from sirius_sdk.messaging import Message, restore_message_instance
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.abstract.p2p import Pairwise

PY_35 = sys.version_info >= (3, 5)
PY_352 = sys.version_info >= (3, 5, 2)


class Listener(AbstractListener):

    def __init__(self, source: AgentEvents, pairwise_resolver: AbstractPairwiseList = None):
        self.__source = source
        self.__pairwise_resolver = pairwise_resolver

    def is_open(self) -> bool:
        return self.__source.is_open

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
