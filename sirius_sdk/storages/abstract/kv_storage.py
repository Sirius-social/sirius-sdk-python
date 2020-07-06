from abc import ABC, abstractmethod
from typing import Any, Optional


class AbstractKeyValueStorage(ABC):

    @abstractmethod
    async def select_db(self, db_name: str):
        raise NotImplemented

    @abstractmethod
    async def set(self, key: str, value: Any):
        raise NotImplemented

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        raise NotImplemented

    @abstractmethod
    async def delete(self, key: str):
        raise NotImplemented
