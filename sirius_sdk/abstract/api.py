from abc import ABC, abstractmethod

from .bus import AbstractBus


class API(ABC):

    @abstractmethod
    async def spawn_coprotocol(self) -> AbstractBus:
        raise NotImplemented
