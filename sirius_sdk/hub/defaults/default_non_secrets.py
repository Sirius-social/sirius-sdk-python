import threading
from typing import Any, List, Optional

from sirius_sdk.abstract.storage import AbstractKeyValueStorage
from sirius_sdk.agent.wallet import RetrieveRecordOptions
from sirius_sdk.agent.wallet.abstract import AbstractNonSecrets


class DefaultNonSecretsStorage(AbstractNonSecrets):

    def __init__(self, storage: AbstractKeyValueStorage):
        self.__storage = storage

    async def add_wallet_record(self, type_: str, id_: str, value: str, tags: dict = None) -> None:
        await self.__storage.select_db(type_)
        meta = await self.__storage.get(id_)
        if meta is not None:
            raise RuntimeError(f'Record with type: {type_} id: {id_} already exists')
        meta = {
            'id': id_,
            'type': type_,
            'value': value,
            'tags': tags or {}
        }
        await self.__storage.set(id_, meta)

    async def update_wallet_record_value(self, type_: str, id_: str, value: str) -> None:
        await self.__storage.select_db(type_)
        meta = await self.__storage.get(id_)
        if meta is None:
            raise RuntimeError(f'Record with type: {type_} id: {id_} does not exists')
        meta['value'] = value
        await self.__storage.set(id_, meta)

    async def update_wallet_record_tags(self, type_: str, id_: str, tags: dict) -> None:
        await self.__storage.select_db(type_)
        meta = await self.__storage.get(id_)
        if meta is None:
            raise RuntimeError(f'Record with type: {type_} id: {id_} does not exists')
        meta['tags'] = tags
        await self.__storage.set(id_, meta)

    async def add_wallet_record_tags(self, type_: str, id_: str, tags: dict) -> None:
        await self.__storage.select_db(type_)
        meta = await self.__storage.get(id_)
        if meta is None:
            raise RuntimeError(f'Record with type: {type_} id: {id_} does not exists')
        stored_tags = meta.get('tags', {})
        meta['tags'] = dict(**tags, **stored_tags)
        await self.__storage.set(id_, meta)

    async def delete_wallet_record_tags(self, type_: str, id_: str, tag_names: List[str]) -> None:
        await self.__storage.select_db(type_)
        meta = await self.__storage.get(id_)
        if meta is None:
            raise RuntimeError(f'Record with type: {type_} id: {id_} does not exists')
        stored_tags = meta.get('tags', {})
        new_tags = {key: val for key, val in stored_tags.items() if key not in tag_names}
        meta['tags'] = new_tags
        await self.__storage.set(id_, meta)

    async def delete_wallet_record(self, type_: str, id_: str) -> None:
        await self.__storage.select_db(type_)
        meta = await self.__storage.get(id_)
        if meta is not None:
            await self.__storage.delete(id_)

    async def get_wallet_record(self, type_: str, id_: str, options: RetrieveRecordOptions) -> Optional[dict]:
        await self.__storage.select_db(type_)
        meta = await self.__storage.get(id_)
        if meta is None:
            raise RuntimeError(f'Record with type: {type_} id: {id_} does not exists')
        ret = self.__build_record(meta, options)
        return ret

    async def wallet_search(self, type_: str, query: dict, options: RetrieveRecordOptions, limit: int = 1) -> (List[dict], int):
        await self.__storage.select_db(type_)
        collection = []
        counter = 0
        d = await self.__storage.items()
        for key, meta in d.items():
            tags = meta.get('tags', {})
            if '$or' in query:
                subs = [{k: v for k, v in tags.items() if k in _or_} for _or_ in query['$or']]
                for sub in subs:
                    success = all([tags[k] == sub[k] for k in sub.keys()])
                    if success:
                        ret = self.__build_record(meta, options)
                        collection.append(ret)
                        counter += 1
                        break
            elif '$in' in query:
                for k, v in tags.items():
                    if v in query['$in']:
                        ret = self.__build_record(meta, options)
                        collection.append(ret)
                        counter += 1
                        break
            else:
                sub = {k: v for k, v in tags.items() if k in query}
                for query_k, query_v in query.items():
                    if type(query_v) is dict and '$in' in query_v:
                        _in_ = query_v['$in']
                        if tags[query_k] in _in_:
                            ret = self.__build_record(meta, options)
                            collection.append(ret)
                            counter += 1
                if sub == query:
                    ret = self.__build_record(meta, options)
                    collection.append(ret)
                    counter += 1
        return collection[:limit], counter

    @staticmethod
    def __build_record(meta: dict, options: RetrieveRecordOptions):
        ret = {'id': meta['id']}
        if options.retrieve_type:
            ret['type'] = meta['type']
        if options.retrieve_tags:
            ret['tags'] = meta['tags']
        if options.retrieve_value:
            ret['value'] = meta['value']
        return ret
