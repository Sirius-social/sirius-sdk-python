from abc import ABC, abstractmethod
from typing import Any, List, Optional, Dict


class AbstractImmutableCollection(ABC):

    @abstractmethod
    async def select_db(self, db_name: str):
        raise NotImplemented

    @abstractmethod
    async def add(self, value: Any, tags: dict):
        raise NotImplemented

    @abstractmethod
    async def fetch(self, tags: dict, limit: int = None) -> (List[Any], int):
        raise NotImplemented


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

    @abstractmethod
    async def items(self) -> Dict:
        raise NotImplemented
