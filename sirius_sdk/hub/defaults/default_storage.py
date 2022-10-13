import threading
from typing import Any, List, Optional, Dict

from sirius_sdk.abstract.storage import AbstractImmutableCollection, AbstractKeyValueStorage
from sirius_sdk.hub.context import get as context_get, set as context_set


def _get_current_hub_id() -> str:
    hub = context_get('hub')
    if hub:
        return hub.global_id
    else:
        return '*'


class InMemoryImmutableCollection(AbstractImmutableCollection):

    __lock_singleton = threading.Lock()
    __selected_db_thread_safe = threading.local()
    __database_singleton = {}

    async def select_db(self, db_name: str):
        mangled_db_name = f'{_get_current_hub_id()}/{db_name}'
        self.__acquire()
        try:
            if mangled_db_name not in self.__database_singleton:
                self.__database_singleton[mangled_db_name] = []
            self.__set_current_db(mangled_db_name)
        finally:
            self.__release()

    async def add(self, value: Any, tags: dict):
        cur_db_name = self.__get_current_db()
        if cur_db_name is None:
            raise RuntimeError('Select working database at first!')
        else:
            self.__acquire()
            try:
                item = (value, tags)
                selected_db = self.__database_singleton[cur_db_name]
                selected_db.append(item)
            finally:
                self.__release()

    async def fetch(self, tags: dict, limit: int = None) -> (List[Any], int):
        cur_db_name = self.__get_current_db()
        if cur_db_name is None:
            raise RuntimeError('Select working database at first!')
        else:
            self.__acquire()
            try:
                result = []
                selected_db = self.__database_singleton[cur_db_name]
                for item in selected_db:
                    value_ = item[0]
                    tags_ = item[1]
                    if tags.items() <= tags_.items():
                        result.append(value_)
                return result
            finally:
                self.__release()

    @classmethod
    def __acquire(cls):
        cls.__lock_singleton.acquire(blocking=True)

    @classmethod
    def __release(cls):
        cls.__lock_singleton.release()

    @classmethod
    def __set_current_db(cls, db_name: str):
        cls.__selected_db_thread_safe.value = db_name

    @classmethod
    def __get_current_db(cls) -> Optional[str]:
        try:
            db = cls.__selected_db_thread_safe.value
        except AttributeError:
            return None
        else:
            return db


class InMemoryKeyValueStorage(AbstractKeyValueStorage):

    __lock_singleton = threading.Lock()
    __selected_db_context_key = 'inmemory.storage.db'
    __database_singleton = {}

    async def select_db(self, db_name: str):
        mangled_db_name = f'{_get_current_hub_id()}/{db_name}'
        self.__acquire()
        try:
            if mangled_db_name not in self.__database_singleton:
                self.__database_singleton[mangled_db_name] = {}
            self.__set_current_db(mangled_db_name)
        finally:
            self.__release()

    async def set(self, key: str, value: Any):
        cur_db_name = self.__get_current_db()
        if cur_db_name is None:
            raise RuntimeError('Select working database at first!')
        else:
            self.__acquire()
            try:
                selected_db = self.__database_singleton[cur_db_name]
                selected_db[key] = value
            finally:
                self.__release()

    async def get(self, key: str) -> Optional[Any]:
        cur_db_name = self.__get_current_db()
        if cur_db_name is None:
            raise RuntimeError('Select working database at first!')
        else:
            self.__acquire()
            try:
                selected_db = self.__database_singleton[cur_db_name]
                return selected_db.get(key, None)
            finally:
                self.__release()

    async def delete(self, key: str):
        cur_db_name = self.__get_current_db()
        if cur_db_name is None:
            raise RuntimeError('Select working database at first!')
        else:
            self.__acquire()
            try:
                selected_db = self.__database_singleton[cur_db_name]
                if key in selected_db:
                    del selected_db[key]
            finally:
                self.__release()

    async def items(self) -> Dict:
        cur_db_name = self.__get_current_db()
        if cur_db_name is None:
            raise RuntimeError('Select working database at first!')
        else:
            self.__acquire()
            try:
                selected_db = self.__database_singleton[cur_db_name]
                copied = dict(**selected_db)
                return copied
            finally:
                self.__release()

    @classmethod
    def __acquire(cls):
        cls.__lock_singleton.acquire(blocking=True)

    @classmethod
    def __release(cls):
        cls.__lock_singleton.release()

    @classmethod
    def __set_current_db(cls, db_name: str):
        context_set(cls.__selected_db_context_key, db_name)

    @classmethod
    def __get_current_db(cls) -> Optional[str]:
        try:
            db = context_get(cls.__selected_db_context_key)
        except AttributeError:
            return None
        else:
            return db
