from abc import ABC, abstractmethod
from typing import List, Any


class ReadOnlyChannel(ABC):

    @abstractmethod
    async def read(self, timeout: int=None) -> Any:
        raise NotImplemented()


class WriteOnlyChannel(ABC):

    @abstractmethod
    async def write(self, data: Any) -> bool:
        raise NotImplemented()


class AddressedTunnel(ReadOnlyChannel):

    def __init__(self, address: str, input_: ReadOnlyChannel, output_: WriteOnlyChannel):
        self.__address = address
        self.__input = input_
        self.__output = output_

    @property
    def address(self):
        return self.__address

    async def read(self, timeout: int=None) -> Any:
        return await self.__input.read(timeout)

    
class BaseConnector(ReadOnlyChannel, WriteOnlyChannel):

    @abstractmethod
    async def open(self):
        raise NotImplemented()

    @abstractmethod
    async def close(self):
        raise NotImplemented()


class Endpoint:

    def __init__(self, address: str, routing_keys: List[str]):
        self.__address = address
        self.__routing_keys = routing_keys

    @property
    def address(self):
        return self.__address

    @property
    def routing_keys(self) -> List[str]:
        return self.__routing_keys
