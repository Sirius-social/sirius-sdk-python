from abc import ABC, abstractmethod
from typing import Optional, List, Generator

from sirius_sdk.messaging import Message
from sirius_sdk.errors.exceptions import SiriusConnectionClosed

from .p2p import Pairwise


class Event(Message):

    def __init__(self, pairwise: Pairwise = None, jwe: bytes = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__pairwise = pairwise
        self.__jwe = jwe

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
    def jwe(self) -> Optional[bytes]:
        return self.__jwe

    @property
    def extra(self) -> Optional[dict]:
        return self.get('~extra', None)


class AbstractListener(ABC):

    @abstractmethod
    def is_open(self) -> bool:
        raise NotImplemented

    @abstractmethod
    async def get_one(self, timeout: int = None) -> Event:
        raise NotImplemented

    def __aiter__(self) -> Generator[Event, None, None]:
        if not self.is_open():
            raise SiriusConnectionClosed()
        return self

    async def __anext__(self):
        while True:
            e = await self.get_one()
            return e
