from typing import Optional, Any

from sirius_sdk.storages.abstract.kv_storage import AbstractKeyValueStorage


class InMemoryKeyValueStorage(AbstractKeyValueStorage):

    def __init__(self, *args, **kwargs):
        self.__databases = {}
        self.__selected_db = None
        super().__init__(*args, **kwargs)

    async def select_db(self, db_name: str):
        if db_name not in self.__databases:
            self.__databases[db_name] = {}
        self.__selected_db = self.__databases[db_name]

    async def set(self, key: str, value: Any):
        self.__selected_db[key] = value

    async def get(self, key: str) -> Optional[Any]:
        return self.__selected_db.get(key, None)

    async def delete(self, key: str):
        if key in self.__selected_db:
            del self.__selected_db[key]
