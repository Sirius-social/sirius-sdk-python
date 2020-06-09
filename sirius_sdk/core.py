from abc import ABC, abstractmethod
from typing import Optional, Any


class ReadOnlyChannel(ABC):

    @abstractmethod
    async def read(self) -> Any:
        raise NotImplemented()


class WriteOnlyChannel(ABC):

    @abstractmethod
    async def write(self, data: Any) -> bool:
        raise NotImplemented()
    
    
class BaseConnector(ReadOnlyChannel, WriteOnlyChannel):

    @abstractmethod
    async def open(self):
        raise NotImplemented()

    @abstractmethod
    async def close(self):
        raise NotImplemented()




