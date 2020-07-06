from typing import Optional, Any, List

from ..abstract.immutable import AbstractImmutableCollection


class InMemoryImmutableCollection(AbstractImmutableCollection):

    def __init__(self, *args, **kwargs):
        self.__databases = {}
        self.__selected_db = None
        super().__init__(*args, **kwargs)

    async def select_db(self, db_name: str):
        if db_name not in self.__databases:
            self.__databases[db_name] = []
        self.__selected_db = self.__databases[db_name]

    async def add(self, value: Any, tags: dict):
        item = (value, tags)
        self.__selected_db.append(item)

    async def fetch(self, tags: dict) -> List[Any]:
        result = []
        for item in self.__selected_db:
            value_ = item[0]
            tags_ = item[1]
            if tags.items() <= tags_.items():
                result.append(value_)
        return result
