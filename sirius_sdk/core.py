from abc import ABC, abstractmethod
from typing import Optional, Any


class ReadOnlyChannel(ABC):

    @abstractmethod
    async def read(self, timeout: int=None) -> Any:
        raise NotImplemented()


class WriteOnlyChannel(ABC):

    @abstractmethod
    async def write(self, data: Any) -> bool:
        raise NotImplemented()


class AddressedTunnel(ReadOnlyChannel):

    def __init__(self, address: str, channel: ReadOnlyChannel):
        self.__address = address
        self.__channel = channel

    @property
    def address(self):
        return self.__address

    async def read(self, timeout: int=None) -> Any:
        return await self.__channel.read(timeout)

    
class BaseConnector(ReadOnlyChannel, WriteOnlyChannel):

    @abstractmethod
    async def open(self):
        raise NotImplemented()

    @abstractmethod
    async def close(self):
        raise NotImplemented()




