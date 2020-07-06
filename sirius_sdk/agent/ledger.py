import logging
from typing import List, Optional

from ..errors.indy_exceptions import LedgerNotFound
from .wallet.abstract.ledger import AbstractLedger
from .wallet.abstract.anoncreds import AnonCredSchema
from .wallet.abstract.cache import AbstractCache, CacheOptions


class Schema(AnonCredSchema):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def seq_no(self) -> int:
        return self.body.get('seqNo', None)

    def __eq__(self, other):
        if isinstance(other, Schema):
            equal = super().__eq__(other)
            if equal:
                return self.seq_no == other.seq_no
            else:
                return False
        else:
            return False


class Ledger:

    def __init__(self, name: str, api: AbstractLedger, cache: AbstractCache):
        self.__name = name
        self._api = api
        self._cache = cache

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
            return True, Schema(**body)
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
            return Schema(**body)
        except LedgerNotFound:
            pass
        ok, ledger_schema = self.register_schema(schema, submitter_did)
        if ok:
            return ledger_schema
        else:
            return None
