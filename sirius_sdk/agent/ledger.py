import json
import copy
import logging
from typing import List, Optional, Union

from sirius_sdk.base import JsonSerializable
from sirius_sdk.storages import AbstractImmutableCollection
from sirius_sdk.errors.indy_exceptions import LedgerNotFound
from sirius_sdk.errors.exceptions import SiriusInvalidPayloadStructure
from sirius_sdk.agent.wallet.abstract.ledger import AbstractLedger
from sirius_sdk.agent.wallet.abstract.anoncreds import AnonCredSchema, AbstractAnonCreds
from sirius_sdk.agent.wallet.abstract.cache import AbstractCache, CacheOptions


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


class CredentialDefinition(JsonSerializable):

    class Config(JsonSerializable):

        def __init__(self):
            self.__support_revocation = False

        @property
        def support_revocation(self) -> bool:
            return self.__support_revocation

        @support_revocation.setter
        def support_revocation(self, value: bool):
            self.__support_revocation = value

        def serialize(self) -> dict:
            return {
                'support_revocation': self.support_revocation
            }

        @classmethod
        def deserialize(cls, buffer: Union[dict, bytes, str]):
            if isinstance(buffer, bytes):
                data = json.loads(buffer.decode())
            elif isinstance(buffer, str):
                data = json.loads(buffer)
            elif isinstance(buffer, dict):
                data = buffer
            else:
                raise RuntimeError('Unexpected buffer Type')
            instance = CredentialDefinition.Config()
            instance.support_revocation = data.get('support_revocation', False)
            return instance

    def __init__(self, tag: str, schema: Schema, config: Config = None, body: dict = None, seq_no: int = None):
        self.__tag = tag
        self.__schema = schema
        self.__config = config or CredentialDefinition.Config()
        self.__body = body
        self.__seq_no = seq_no

    @property
    def tag(self) -> str:
        return self.__tag

    @property
    def id(self) -> Optional[str]:
        if self.body:
            return self.body.get('id', None)
        else:
            return None

    @property
    def submitter_did(self) -> Optional[str]:
        if self.id:
            parts = self.id.split(':')
            return parts[0]
        else:
            return None

    @property
    def seq_no(self) -> Optional[int]:
        return self.__seq_no

    @property
    def schema(self) -> Schema:
        return self.__schema

    @property
    def config(self) -> Config:
        return self.__config

    @property
    def body(self) -> dict:
        return self.__body

    def serialize(self) -> dict:
        return {
            'schema': self.schema.serialize(),
            'config': self.config.serialize(),
            'body': self.body,
            'seq_no': self.seq_no
        }

    @classmethod
    def deserialize(cls, buffer: Union[dict, bytes, str]):
        if isinstance(buffer, bytes):
            data = json.loads(buffer.decode())
        elif isinstance(buffer, str):
            data = json.loads(buffer)
        elif isinstance(buffer, dict):
            data = buffer
        else:
            raise RuntimeError('Unexpected buffer Type')
        schema = Schema.deserialize(data['schema'])
        config = CredentialDefinition.Config.deserialize(data['config'])
        body = data['body']
        seq_no = data['seq_no']
        return CredentialDefinition(body['tag'], schema, config, body, seq_no)


class CredentialDefinitionFilters:

    def __init__(self):
        self.__extras = {}
        self.__tags = {'category': 'cred_def'}

    @property
    def tags(self) -> dict:
        d = copy.copy(self.__tags)
        d.update(self.__extras)
        return d

    @property
    def extras(self) -> dict:
        return self.__extras

    @extras.setter
    def extras(self, value: dict):
        self.__extras = value

    def extra(self, name: str, value: str):
        self.__extras[name] = value

    @property
    def tag(self) -> Optional[str]:
        return self.__tags.get('tag', None)

    @tag.setter
    def tag(self, value: str):
        if value:
            self.__tags['tag'] = value
        elif 'tag' in self.__tags:
            del self.__tags['tag']

    @property
    def id(self) -> Optional[str]:
        return self.__tags.get('id', None)

    @id.setter
    def id(self, value: str):
        self.__tags['id'] = value

    @property
    def submitter_did(self) -> Optional[str]:
        return self.__tags.get('submitter_did', None)

    @submitter_did.setter
    def submitter_did(self, value: str):
        self.__tags['submitter_did'] = value

    @property
    def schema_id(self) -> Optional[str]:
        return self.__tags.get('schema_id', None)

    @schema_id.setter
    def schema_id(self, value: str):
        self.__tags['schema_id'] = value

    @property
    def seq_no(self) -> Optional[int]:
        value = self.__tags.get('seq_no', None)
        return int(value) if value else None

    @seq_no.setter
    def seq_no(self, value: int):
        self.__tags['seq_no'] = str(value)


class Ledger:

    def __init__(
            self, name: str, api: AbstractLedger, issuer: AbstractAnonCreds,
            cache: AbstractCache, storage: AbstractImmutableCollection
    ):
        self.__name = name
        self._api = api
        self._cache = cache
        self._issuer = issuer
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

    async def load_cred_def(self, id_: str, submitter_did: str) -> CredentialDefinition:
        cred_def_body = await self._cache.get_cred_def(
            pool_name=self.name,
            submitter_did=submitter_did,
            id_=id_,
            options=CacheOptions()
        )
        tag = cred_def_body.get('tag')
        schema_seq_no = int(cred_def_body['schemaId'])
        cred_def_seq_no = int(cred_def_body['id'].split(':')[3]) + 1
        txn_request = await self._api.build_get_txn_request(
            submitter_did=submitter_did,
            ledger_type=None,
            seq_no=schema_seq_no
        )
        resp = await self._api.sign_and_submit_request(
            pool_name=self.name,
            submitter_did=submitter_did,
            request=txn_request
        )
        if resp['op'] == 'REPLY':
            txn_data = resp['result']['data']
            schema_body = {
                'name': txn_data['txn']['data']['data']['name'],
                'version': txn_data['txn']['data']['data']['version'],
                'attrNames': txn_data['txn']['data']['data']['attr_names'],
                'id': txn_data['txnMetadata']['txnId'],
                'seqNo': txn_data['txnMetadata']['seqNo']
            }
            schema_body['ver'] = schema_body['id'].split(':')[-1]
            schema = Schema(**schema_body)
            cred_def = CredentialDefinition(
                tag=tag, schema=schema, body=cred_def_body, seq_no=cred_def_seq_no
            )
            return cred_def
        else:
            raise SiriusInvalidPayloadStructure()

    async def register_schema(self, schema: AnonCredSchema, submitter_did: str) -> (bool, Schema):
        success, txn_response = await self._api.register_schema(
            pool_name=self.name,
            submitter_did=submitter_did,
            data=schema.body
        )
        if success and txn_response.get('op') == 'REPLY':
            body = copy.copy(schema.body)
            body['seqNo'] = txn_response['result']['txnMetadata']['seqNo']
            schema_in_ledger = Schema(**body)
            await self.__ensure_exists_in_storage(schema_in_ledger, submitter_did)
            return True, schema_in_ledger
        else:
            reason = txn_response.get('reason', None)
            if reason:
                logging.error(reason)
            return False, None

    async def register_cred_def(
            self, cred_def: CredentialDefinition, submitter_did: str, tags: dict = None
    ) -> (bool, CredentialDefinition):
        cred_def_id, body = await self._issuer.issuer_create_and_store_credential_def(
            issuer_did=submitter_did,
            schema=cred_def.schema.body,
            tag=cred_def.tag,
            config=cred_def.config.serialize()
        )
        build_request = await self._api.build_cred_def_request(
            submitter_did=submitter_did,
            data=body
        )
        signed_request = await self._api.sign_request(
            submitter_did=submitter_did,
            request=build_request
        )
        resp = await self._api.submit_request(self.name, signed_request)
        success = resp.get('op', None) == 'REPLY'
        if success:
            txn_response = resp
        else:
            return False, None
        if success:
            ledger_cred_def = CredentialDefinition(
                tag=cred_def.tag,
                schema=cred_def.schema,
                config=cred_def.config,
                body=body,
                seq_no=txn_response['result']['txnMetadata']['seqNo']
            )
            await self.__ensure_exists_in_storage(ledger_cred_def, submitter_did, tags)
            return True, ledger_cred_def

    async def ensure_schema_exists(self, schema: AnonCredSchema, submitter_did: str) -> Optional[Schema]:
        try:
            body = await self._cache.get_schema(
                pool_name=self.name,
                submitter_did=submitter_did,
                id_=schema.id,
                options=CacheOptions()
            )
            ledger_schema = Schema(**body)
            await self.__ensure_exists_in_storage(ledger_schema, submitter_did)
            return ledger_schema
        except LedgerNotFound:
            pass
        ok, ledger_schema = self.register_schema(schema, submitter_did)
        if ok:
            return ledger_schema
        else:
            return None

    async def fetch_schemas(
            self, id_: str = None, name: str = None, version: str = None, submitter_did: str = None
    ) -> List[Schema]:
        filters = SchemaFilters()
        if id_:
            filters.id = id_
        if name:
            filters.name = name
        if version:
            filters.version = version
        if submitter_did:
            filters.submitter_did = submitter_did
        fetched, total_count = await self._storage.fetch(filters.tags)
        return [Schema.deserialize(item) for item in fetched]

    async def fetch_cred_defs(
            self, tag: str = None, id_: str = None, submitter_did: str = None,
            schema_id: str = None, seq_no: int = None, **kwargs
    ) -> List[CredentialDefinition]:
        filters = CredentialDefinitionFilters()
        if tag:
            filters.tag = tag
        if id_:
            filters.id = id_
        if submitter_did:
            filters.submitter_did = submitter_did
        if schema_id:
            filters.schema_id = schema_id
        if seq_no:
            filters.seq_no = seq_no
        filters.extras = kwargs
        fetched, total_count = await self._storage.fetch(filters.tags)
        return [CredentialDefinition.deserialize(item) for item in fetched]

    async def __ensure_exists_in_storage(
            self, entity: Union[Schema, CredentialDefinition], submitter_did: str, search_tags: dict = None
    ):
        await self._storage.select_db(self.__db)
        if isinstance(entity, Schema):
            schema = entity
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
        elif isinstance(entity, CredentialDefinition):
            cred_def = entity
            tags = {
                'id': cred_def.id,
                'seq_no': str(cred_def.seq_no),
                'category': 'cred_def'
            }
            _, count = await self._storage.fetch(tags=tags)
            if count == 0:
                tags.update(
                    {
                        'id': cred_def.id,
                        'tag': cred_def.tag,
                        'schema_id': cred_def.schema.id,
                        'submitter_did': cred_def.submitter_did
                    }
                )
                if search_tags:
                    tags.update(search_tags)
                await self._storage.add(
                    value=cred_def.serialize(),
                    tags=tags
                )
