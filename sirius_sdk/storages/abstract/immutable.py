from abc import ABC, abstractmethod
from typing import Any, List


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
