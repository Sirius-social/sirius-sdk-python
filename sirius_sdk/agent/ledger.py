import json
import logging
from typing import List, Optional, Union

from ..base import JsonSerializable
from ..storages import AbstractImmutableCollection
from ..errors.indy_exceptions import LedgerNotFound
from .wallet.abstract.ledger import AbstractLedger
from .wallet.abstract.anoncreds import AnonCredSchema
from .wallet.abstract.cache import AbstractCache, CacheOptions


class Schema(AnonCredSchema, JsonSerializable):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def seq_no(self) -> int:
        return self.body.get('seqNo', None)

    @property
    def issuer_did(self) -> str:
        parts = self.id.split(':')
        return parts[0]

    def __eq__(self, other):
        if isinstance(other, Schema):
            equal = super().__eq__(other)
            if equal:
                return self.seq_no == other.seq_no
            else:
                return False
        else:
            return False

    def serialize(self) -> dict:
        return self.body

    @classmethod
    def deserialize(cls, buffer: Union[dict, bytes, str]):
        if isinstance(buffer, bytes):
            kwargs = json.loads(buffer.decode())
        elif isinstance(buffer, str):
            kwargs = json.loads(buffer)
        elif isinstance(buffer, dict):
            kwargs = buffer
        else:
            raise RuntimeError('Unexpected buffer Type')
        return Schema(**kwargs)


class SchemaFilters:

    def __init__(self):
        self.__tags = {'category': 'schema'}

    @property
    def tags(self) -> dict:
        return self.__tags

    @property
    def id(self) -> Optional[str]:
        return self.__tags.get('id', None)

    @id.setter
    def id(self, value: str):
        self.__tags['id'] = value

    @property
    def name(self) -> Optional[str]:
        return self.__tags.get('name', None)

    @name.setter
    def name(self, value: str):
        self.__tags['name'] = value

    @property
    def version(self) -> Optional[str]:
        return self.__tags.get('version', None)

    @version.setter
    def version(self, value: str):
        self.__tags['version'] = value

    @property
    def submitter_did(self) -> Optional[str]:
        return self.__tags.get('submitter_did', None)

    @submitter_did.setter
    def submitter_did(self, value: str):
        self.__tags['submitter_did'] = value


class Ledger:

    def __init__(self, name: str, api: AbstractLedger, cache: AbstractCache, storage: AbstractImmutableCollection):
        self.__name = name
        self._api = api
        self._cache = cache
        self._storage = storage
        self.__db = 'ledger_storage_%s' % name

    @property
    def name(self) -> str:
        return self.__name

    async def load_schema(self, id_: str, submitter_did: str) -> Schema:
        body = await self._cache.get_schema(
            pool_name=self.name,
            submitter_did=submitter_did,
            id_=id_,
            options=CacheOptions()
        )
        return Schema(**body)

    async def register_schema(self, schema: AnonCredSchema, submitter_did: str) -> (bool, Schema):
        success, txn_response = await self._api.register_schema(
            pool_name=self.name,
            submitter_did=submitter_did,
            data=schema.body
        )
        if success and txn_response.get('op') == 'REPLY':
            body = schema.body
            body['seqNo'] = txn_response['result']['txnMetadata']['seqNo']
            schema_in_ledger = Schema(**body)
            await self._ensure_exists_in_storage(schema_in_ledger, submitter_did)
            return True, schema_in_ledger
        else:
            reason = txn_response.get('reason', None)
            if reason:
                logging.error(reason)
            return False, None

    async def ensure_schema_exists(self, schema: AnonCredSchema, submitter_did: str) -> Optional[Schema]:
        try:
            body = await self._cache.get_schema(
                pool_name=self.name,
                submitter_did=submitter_did,
                id_=schema.id,
                options=CacheOptions()
            )
            ledger_schema = Schema(**body)
            await self._ensure_exists_in_storage(ledger_schema, submitter_did)
            return ledger_schema
        except LedgerNotFound:
            pass
        ok, ledger_schema = self.register_schema(schema, submitter_did)
        if ok:
            return ledger_schema
        else:
            return None

    async def fetch_schemas(self, filters: SchemaFilters) -> List[Schema]:
        fetched, total_count = await self._storage.fetch(filters.tags)
        return [Schema.deserialize(item) for item in fetched]

    async def _ensure_exists_in_storage(self, schema: Schema, submitter_did: str):
        await self._storage.select_db(self.__db)
        tags = {
            'id': schema.id,
            'category': 'schema'
        }
        _, count = await self._storage.fetch(tags=tags)
        if count == 0:
            tags.update(
                {
                    'id': schema.id,
                    'name': schema.name,
                    'version': schema.version,
                    'submitter_did': submitter_did
                }
            )
            await self._storage.add(
                value=schema.serialize(),
                tags=tags
            )
