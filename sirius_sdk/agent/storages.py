import json
import uuid
from typing import List, Any

from sirius_sdk.base import JsonSerializable
from sirius_sdk.storages import AbstractImmutableCollection
from sirius_sdk.agent.wallet.abstract.non_secrets import AbstractNonSecrets, RetrieveRecordOptions


class InWalletImmutableCollection(AbstractImmutableCollection):

    DEFAULT_FETCH_LIMIT = 1000

    def __init__(self, in_wallet_storage: AbstractNonSecrets, *args, **kwargs):
        self._storage = in_wallet_storage
        self._selected_db = None
        super().__init__(*args, **kwargs)

    async def select_db(self, db_name: str):
        self._selected_db = db_name

    async def add(self, value: Any, tags: dict):
        payload = json.dumps(value)
        await self._storage.add_wallet_record(
            type_=self._selected_db,
            id_=uuid.uuid4().hex,
            value=payload,
            tags=tags
        )

    async def fetch(self, tags: dict, limit: int=None) -> (List[Any], int):
        collection, total_count = await self._storage.wallet_search(
            type_=self._selected_db,
            query=tags,
            options=RetrieveRecordOptions(retrieve_value=True),
            limit=limit or self.DEFAULT_FETCH_LIMIT
        )
        if collection:
            return [json.loads(item['value']) for item in collection], total_count
        else:
            return [], total_count
