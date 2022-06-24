from abc import ABC, abstractmethod

from sirius_sdk.errors.exceptions import SiriusTimeoutIO


class AbstractBus(ABC):
    """Bus concept covers problematic of wall between trust domains, typically born in combination of user-space code
    that have access to personal data
    and outdoor service that operate with low-level transport and don't have access to user-space semantic.

    Bus can help to resolve this: low-level transport services don't have access to semantic (thread-ids is not
    informative entity) on other hands user-space operations flow can run co-protocols and exchange data
    without dependency of location
    """

    @abstractmethod
    async def subscribe(self, thid: str) -> bool:
        """Subscribe to events from stream marked with specific thread-id

        returns: success flag
        """
        raise NotImplemented

    @abstractmethod
    async def unsubscribe(self, thid: str):
        """UnSubscribe from events stream marked with specific thread-id
        """
        raise NotImplemented

    @abstractmethod
    async def publish(self, thid: str, payload: bytes) -> int:
        """Publish data to events stream marked with thread-id

        returns: num of active recipients
        """
        raise NotImplemented

    @abstractmethod
    async def get_event(self, timeout: float = None) -> bytes:
        """Wait event on streams earlier subscribed

        :param timeout: wait timeout, raises SiriusTimeoutIO if timeout occurred
        returns event data in bytes
        """
        raise NotImplemented
