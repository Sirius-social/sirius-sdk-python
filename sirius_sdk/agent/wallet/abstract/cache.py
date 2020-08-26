import json
from abc import ABC, abstractmethod

from sirius_sdk.base import JsonSerializable


class CacheOptions(JsonSerializable):

    def __init__(self, no_cache: bool=False, no_update: bool=False, no_store: bool=False, min_fresh: int=-1):
        """
        :param no_cache: (bool, optional, false by default) Skip usage of cache,
        :param no_update: (bool, optional, false by default) Use only cached data, do not try to update.
        :param no_store: (bool, optional, false by default) Skip storing fresh data if updated,
        :param min_fresh: (int, optional, -1 by default) Return cached data if not older than this many seconds. -1 means do not check age.
        """
        self.no_cache = no_cache
        self.no_update = no_update
        self.no_store = no_store
        self.min_fresh = min_fresh

    def to_json(self):
        return {
           'noCache': self.no_cache,
           'noUpdate': self.no_update,
           'noStore': self.no_store,
           'minFresh': self.min_fresh
        }

    def serialize(self):
        return json.dumps(self.to_json())

    def deserialize(self, buffer: str):
        data = json.loads(buffer)
        self.no_cache = data.get('noCache', False)
        self.no_update = data.get('noUpdate', False)
        self.no_store = data.get('noStore', False)
        self.min_fresh = data.get('minFresh', -1)


class PurgeOptions(JsonSerializable):

    def __init__(self, max_age: int=-1):
        self.max_age = max_age

    def to_json(self):
        return {
           'maxAge': self.max_age
        }

    def serialize(self):
        return json.dumps(self.to_json())

    def deserialize(self, buffer: str):
        data = json.loads(buffer)
        self.max_age = data.get('maxAge', -1)


class AbstractCache(ABC):

    @abstractmethod
    async def get_schema(self, pool_name: str, submitter_did: str, id_: str, options: CacheOptions) -> dict:
        """
        Gets schema json data for specified schema id.
        If data is present inside of cache, cached data is returned.
        Otherwise data is fetched from the ledger and stored inside of cache for future use.

        EXPERIMENTAL

        :param pool_name: Ledger.
        :param submitter_did: DID of the submitter stored in secured Wallet.
        :param id_: identifier of schema.
        :param options:
        {
            noCache: (bool, optional, false by default) Skip usage of cache,
            noUpdate: (bool, optional, false by default) Use only cached data, do not try to update.
            noStore: (bool, optional, false by default) Skip storing fresh data if updated,
            minFresh: (int, optional, -1 by default) Return cached data if not older than this many seconds. -1 means do not check age.
        }
        :return: Schema json.
        {
            id: identifier of schema
            attrNames: array of attribute name strings
            name: Schema's name string
            version: Schema's version string
            ver: Version of the Schema json
        }
        """
        raise NotImplemented

    @abstractmethod
    async def get_cred_def(self, pool_name: str, submitter_did: str, id_: str, options: CacheOptions) -> dict:
        """
        Gets credential definition json data for specified credential definition id.
        If data is present inside of cache, cached data is returned.
        Otherwise data is fetched from the ledger and stored inside of cache for future use.

        EXPERIMENTAL

        :param pool_name: Ledger.
        :param submitter_did: DID of the submitter stored in secured Wallet.
        :param id_: identifier of credential definition.
        :param options:
        {
            noCache: (bool, optional, false by default) Skip usage of cache,
            noUpdate: (bool, optional, false by default) Use only cached data, do not try to update.
            noStore: (bool, optional, false by default) Skip storing fresh data if updated,
            minFresh: (int, optional, -1 by default) Return cached data if not older than this many seconds. -1 means do not check age.
        }
        :return: Credential Definition json.
        {
            id: string - identifier of credential definition
            schemaId: string - identifier of stored in ledger schema
            type: string - type of the credential definition. CL is the only supported type now.
            tag: string - allows to distinct between credential definitions for the same issuer and schema
            value: Dictionary with Credential Definition's data: {
                primary: primary credential public key,
                Optional<revocation>: revocation credential public key
            },
            ver: Version of the Credential Definition json
        }
        """
        raise NotImplemented

    @abstractmethod
    async def purge_schema_cache(self, options: PurgeOptions) -> None:
        """
        Purge schema cache.

        EXPERIMENTAL

        :param options:
        {
            maxAge: (int, optional, -1 by default) Purge cached data if older than this many seconds. -1 means purge all.
        }
        :return: None
        """
        raise NotImplemented

    @abstractmethod
    async def purge_cred_def_cache(self, options: PurgeOptions) -> None:
        """
        Purge credential definition cache.

        EXPERIMENTAL

        :param options:
        {
            maxAge: (int, optional, -1 by default) Purge cached data if older than this many seconds. -1 means purge all.
        }
        :return: None
        """
        raise NotImplemented
