from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List

from sirius_sdk.messaging import Message


class AbstractBus(ABC):
    """Bus concept covers problematic of wall between trust domains, typically born in combination of user-space code
    that have access to personal data
    and outdoor service that operate with low-level transport and don't have access to user-space semantic.

    Bus can help to resolve this: low-level transport services don't have access to semantic (thread-ids is not
    informative entity) on other hands user-space operations flow can run co-protocols and exchange data
    without dependency of location
    """

    @dataclass
    class BytesEvent:
        thread_id: str
        payload: bytes

    @dataclass
    class MessageEvent:
        thread_id: str
        message: Message
        sender_verkey: Optional[str]
        recipient_verkey: Optional[str]

    @abstractmethod
    async def subscribe(self, thid: str) -> bool:
        """Subscribe to events from stream marked with specific thread-id

        returns: success flag
        """
        raise NotImplemented

    @abstractmethod
    async def subscribe_ext(self, sender_vk: List[str], recipient_vk: List[str], protocols: List[str]) -> (bool, List[str]):
        """Subscribe to events that addressed by verkeys and protocol-names

         - Assumed bus agent has access to wallet secrets, so it is case fow cloud wallet agents

        returns: success flag, list of binding ids
        """
        raise NotImplemented

    @abstractmethod
    async def unsubscribe(self, thid: str):
        """UnSubscribe from events stream marked with specific thread-id
        """
        raise NotImplemented

    @abstractmethod
    async def unsubscribe_ext(self, thids: List[str]):
        """UnSubscribe from events stream marked with specific binding-ids
        """
        raise NotImplemented

    @abstractmethod
    async def publish(self, thid: str, payload: bytes) -> int:
        """Publish data to events stream marked with thread-id

        returns: num of active recipients
        """
        raise NotImplemented

    @abstractmethod
    async def get_event(self, timeout: float = None) -> BytesEvent:
        """Wait event on streams earlier subscribed

        :param timeout: wait timeout, raises SiriusTimeoutIO if timeout occurred
        returns event data in bytes
        """
        raise NotImplemented

    @abstractmethod
    async def get_message(self, timeout: float = None) -> MessageEvent:
        """Wait message on streams earlier subscribed

        :param timeout: wait timeout, raises SiriusTimeoutIO if timeout occurred
        returns parsed message
        """
        raise NotImplemented

    @abstractmethod
    async def abort(self):
        """Abort all active subscribers with raising OperationAbortedManually exception"""
        raise NotImplemented
