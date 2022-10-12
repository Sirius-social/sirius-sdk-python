import datetime
import hashlib
import json
import os.path
import uuid
from urllib.parse import urlparse

from typing import List, Optional, Tuple, Any

import sirius_sdk
from sirius_sdk.agent.aries_rfc.feature_0750_storage import EncryptedDataVault, StructuredDocument, \
    ConfidentialStorageAuthProvider, VaultConfig, ConfidentialStorageRawByteStorage, FileSystemRawByteStorage, \
    StreamEncryption, AbstractWriteOnlyStream, AbstractReadOnlyStream, EncryptedDocument, DataVaultStreamWrapper, \
    StreamDecryption, StreamMeta, DocumentMeta
from sirius_sdk.agent.aries_rfc.feature_0750_storage.errors import *
from sirius_sdk.agent.aries_rfc.feature_0750_storage.encoding import ConfidentialStorageEncType
from sirius_sdk.agent.aries_rfc.feature_0750_storage.impl.file_system import FileSystemWriteOnlyStream


class SimpleDataVault(EncryptedDataVault, EncryptedDataVault.Indexes):

    STORAGE_TYPE = 'data_vault'

    # Meta
    META_CREATED_ATTR = 'created'
    META_CONTENT_TYPE_ATTR = 'contentType'
    META_CREATED_CHUNKS_ATTR = 'chunks'
    RESERVED_META_ATTRS = [META_CREATED_ATTR, META_CONTENT_TYPE_ATTR, META_CREATED_CHUNKS_ATTR]

    # Attributes
    ATTR_IS_STREAM = '__is_stream'
    ATTR_CHUNKS_NUM = '__chunks_num'
    ATTR_CHUNK_SIZE = '__chunk_size'
    ATTR_URN = '__urn'
    RESERVED_ATTRIBS = [ATTR_IS_STREAM, ATTR_CHUNKS_NUM, ATTR_CHUNK_SIZE, ATTR_URN]

    def __init__(self, mounted_dir: str, auth: ConfidentialStorageAuthProvider, cfg: VaultConfig = None):
        if not os.path.isdir(mounted_dir):
            raise RuntimeError(f'Directory "{mounted_dir}" does not exists')
        super().__init__(auth, cfg)
        self.__mounted_dir = os.path.join(mounted_dir, f'vault_{auth.entity.their.did}')
        if not os.path.isdir(self.__mounted_dir):
            os.mkdir(self.__mounted_dir)
        self.__storage: Optional[ConfidentialStorageRawByteStorage] = None
        self.__cached_info: Tuple[str, dict] = ('', {})
        self.__is_open: bool = False

    @property
    def mounted_dir(self) -> str:
        return self.__mounted_dir

    @property
    def is_open(self) -> bool:
        return self.__is_open

    async def open(self):
        if not self.__is_open:
            self.__storage = await self._mounted()
            self.__is_open = True

    async def close(self):
        if self.__is_open:
            if self.__storage is not None:
                self.__storage = None
            self.__is_open = False

    async def indexes(self) -> EncryptedDataVault.Indexes:
        self.auth.validate(can_read=True)
        return self

    async def create_stream(self, uri: str, meta:  Union[dict, StreamMeta] = None, chunk_size: int = None, **attributes) -> StructuredDocument:
        self.__check_is_open()
        uri = self.__normalize_uri(uri)
        await self.__create_resource(uri, is_stream=True, meta=meta, chunk_size=chunk_size, **attributes)
        info = await self.__load_resource_info(uri)
        meta = self.__extract_meta_from_info(info)
        attrib_as_dict = self.__extract_attributed_from_info(info)
        urn = info['tags'].get(self.ATTR_URN, None)
        uri = info['id']
        return StructuredDocument(
            id_=uri, meta=meta, content=None, urn=urn,
            indexed=[StructuredDocument.Index(sequence=0, attributes=list(attrib_as_dict.keys()))],
            stream=DataVaultStreamWrapper(
                readable=await self.readable(uri) if self.auth.can_read else None,
                writable=await self.writable(uri) if self.auth.can_write else None
            )
        )

    async def create_document(self, uri: str, meta: Union[dict, DocumentMeta] = None, **attributes) -> StructuredDocument:
        self.__check_is_open()
        uri = self.__normalize_uri(uri)
        await self.__create_resource(uri, is_stream=False, meta=meta, **attributes)
        info = await self.__load_resource_info(uri)
        meta = self.__extract_meta_from_info(info)
        attrib_as_dict = self.__extract_attributed_from_info(info)
        urn = info['tags'].get(self.ATTR_URN, None)
        uri = info['id']
        return StructuredDocument(
            id_=uri, meta=meta,
            content=EncryptedDocument(content=None),
            urn=urn,
            indexed=[StructuredDocument.Index(sequence=0, attributes=list(attrib_as_dict.keys()))]
        )

    async def remove(self, uri: str):
        info = await self.__load_resource_info(uri)
        if info:
            uri = info['id']
        await self.__remove_resource(uri, only_infos=False)

    async def update(self, uri: str, meta: Union[dict, DocumentMeta, StreamMeta] = None, **attributes):
        self.__check_is_open()
        self.auth.validate(can_update=True)
        uri = self.__normalize_uri(uri)
        info = await self.__load_resource_info(uri)
        if info is None:
            raise DataVaultResourceMissing(f'Mission resource uri: {uri}')
        stored_meta = self.__extract_meta_from_info(info)
        cleaned_meta = {k: v for k, v in stored_meta.items() if k in self.RESERVED_META_ATTRS}
        new_meta = dict(**meta)
        new_meta.update(cleaned_meta)
        tags = info['tags']
        new_tags = self.__clean_income_attributes(**attributes)
        # save old reserved attrs: rewrite new ones
        new_tags.update({k: v for k, v in tags.items() if k in self.RESERVED_ATTRIBS})
        await sirius_sdk.NonSecrets.update_wallet_record_value(type_=self._storage_type, id_=uri, value=json.dumps(new_meta))
        await sirius_sdk.NonSecrets.update_wallet_record_tags(type_=self._storage_type, id_=uri, tags=new_tags)
        self.__clean_caches()

    async def load(self, uri: str) -> StructuredDocument:
        self.__check_is_open()
        self.auth.validate(can_read=True)
        storage = await self._mounted()
        info = await self.__load_resource_info(uri)
        if info:
            uri = info['id']
        if info is None or not await storage.exists(uri):
            raise DataVaultResourceMissing(f'Mission resource uri: {uri}')
        urn = info['tags'].get(self.ATTR_URN, None)
        meta = self.__extract_meta_from_info(info)
        is_stream = info['tags'].get(self.ATTR_IS_STREAM, None) != 'no'
        chunks_num = int(info['tags'].get(self.ATTR_CHUNKS_NUM, '0'))
        storage = await self._mounted()
        attrib_as_dict = self.__extract_attributed_from_info(info)
        indexed = [StructuredDocument.Index(sequence=0, attributes=list(attrib_as_dict.keys()))]
        if is_stream:
            if self.META_CREATED_CHUNKS_ATTR not in meta:
                meta[self.META_CREATED_CHUNKS_ATTR] = int(chunks_num)
            if self.auth.can_read or self.auth.can_write:
                stream_wrapper = DataVaultStreamWrapper(
                    readable=await self.readable(uri) if self.auth.can_read else None,
                    writable=await self.writable(uri) if self.auth.can_write else None
                )
            else:
                stream_wrapper = None
            return StructuredDocument(id_=uri, meta=meta, content=None, stream=stream_wrapper, urn=urn, indexed=indexed)
        else:
            if chunks_num > 0:
                stream = await storage.readable(uri, chunks_num)
                await stream.open()
                try:
                    doc = EncryptedDocument()
                    await doc.load(stream)
                    # try detect is encrypted
                    try:
                        o = json.loads(doc.content.decode())
                        if 'protected' in o:
                            doc.encrypted = True
                    except json.JSONDecodeError:
                        pass
                    return StructuredDocument(id_=uri, meta=meta, content=doc, urn=urn, indexed=indexed)
                finally:
                    await stream.close()
            else:
                doc = EncryptedDocument()
                doc.content = None
                return StructuredDocument(id_=uri, meta=meta, content=doc, urn=urn, indexed=indexed)

    async def save_document(self, uri: str, doc: EncryptedDocument):
        self.__check_is_open()
        self.auth.validate(can_write=True)
        info = await self.__load_resource_info(uri)
        if info is None:
            raise DataVaultResourceMissing(f'Mission resource uri: {uri}')
        if info['tags'][self.ATTR_IS_STREAM] != 'no':
            raise StreamInitializationError(f'Resource uri: "{uri}" is stream, you can not operate as document with it')
        tags = info['tags']
        uri = info['id']
        storage = await self._mounted()
        stream = await storage.writeable(uri)
        await stream.open()
        try:
            await doc.save(stream)
            tags.update({self.ATTR_CHUNKS_NUM: str(stream.chunks_num)})
            await sirius_sdk.NonSecrets.update_wallet_record_tags(
                type_=self._storage_type, id_=uri, tags=tags
            )
        finally:
            await stream.close()

    async def readable(self, uri: str) -> AbstractReadOnlyStream:
        self.__check_is_open()
        self.auth.validate(can_read=True)
        info = await self.__load_resource_info(uri)
        if info is None:
            raise DataVaultResourceMissing(f'Mission resource uri: {uri}')
        if info['tags'][self.ATTR_IS_STREAM] != 'yes':
            raise StreamInitializationError(f'Resource uri: "{uri}" is not stream')
        chunks_num = int(info['tags'].get(self.ATTR_CHUNKS_NUM, '0'))
        storage = await self._mounted()
        stream = await storage.readable(uri, chunks_num)
        return stream

    async def writable(self, uri: str) -> AbstractWriteOnlyStream:
        self.__check_is_open()
        self.auth.validate(can_write=True)
        info = await self.__load_resource_info(uri)
        if info is None:
            raise DataVaultResourceMissing(f'Mission resource uri: {uri}')
        if info['tags'][self.ATTR_IS_STREAM] != 'yes':
            raise StreamInitializationError(f'Resource uri: "{uri}" is not stream')
        storage = await self._mounted()
        stream = await storage.writeable(uri)
        stored_chunk_size = info['tags'].get(self.ATTR_CHUNK_SIZE, 'null')
        if stored_chunk_size != 'null':
            stream.chunk_size = int(stored_chunk_size)
        if isinstance(stream, FileSystemWriteOnlyStream):

            async def __on_close__(uri_: str, tags_: dict, s_: AbstractWriteOnlyStream):
                # Update stream metadata on close
                tags_.update({self.ATTR_CHUNKS_NUM: str(s_.chunks_num)})
                await sirius_sdk.NonSecrets.update_wallet_record_tags(
                    type_=self._storage_type, id_=uri_, tags=tags_
                )

            stream.on_closed = __on_close__(uri, info['tags'], stream)
        return stream

    async def filter(self, **attributes) -> List[StructuredDocument]:
        self.__check_is_open()
        opts = sirius_sdk.NonSecretsRetrieveRecordOptions()
        opts.check_all()
        limit = 10000
        kwargs = dict(type_=self._storage_type, query=dict(**attributes), options=opts)
        collection, total = await sirius_sdk.NonSecrets.wallet_search(**kwargs, limit=limit)
        if total > limit:
            collection, _ = await sirius_sdk.NonSecrets.wallet_search(**kwargs, limit=total)
        ret = []
        if collection is None:
            collection = []
        missing_resources = []
        for item in collection:
            try:
                doc = await self.load(uri=item['id'])
            except DataVaultResourceMissing:
                missing_resources.append(item['id'])
            else:
                ret.append(doc)
        for uri in missing_resources:
            await self.__remove_resource(uri, only_infos=True)
        return ret

    async def _mounted(self) -> ConfidentialStorageRawByteStorage:
        if self.__storage is None:
            if self.cfg.key_agreement is None:
                encryption = None
            else:
                if self.cfg.key_agreement.type == ConfidentialStorageEncType.UNKNOWN.value:
                    encryption = StreamEncryption(type_=ConfidentialStorageEncType.UNKNOWN)
                else:
                    if not self.cfg.key_agreement.type.startswith('X25519'):
                        raise EncryptionError(f'Unsupported key agreement type: "{self.cfg.key_agreement.type}"')
                    storage_id = hashlib.md5(self.__mounted_dir.encode()).hexdigest()
                    # Try to load encryption settings
                    encryption = await self.__load_storage_encryption(storage_id)
                    if encryption is None:
                        # Initialize encryption settings
                        encryption = StreamEncryption(type_=ConfidentialStorageEncType.X25519KeyAgreementKey2019)
                        if self.cfg.key_agreement.id.startswith('did:key:'):
                            target_verkey = self.cfg.key_agreement.id.split(':')[-1]
                        else:
                            target_verkey = self.cfg.key_agreement.id
                        encryption.setup(target_verkeys=[target_verkey])
                        await self.__init_storage_encryption(storage_id, encryption)
                pass
            #
            self.__storage = FileSystemRawByteStorage(encryption=encryption)
            await self.__storage.mount(self.__mounted_dir)
        return self.__storage

    async def __load_resource_info(self, uri: str) -> Optional[dict]:
        cached_uri, cached_info = self.__cached_info
        if cached_uri == uri:
            return cached_info
        opts = sirius_sdk.NonSecretsRetrieveRecordOptions()
        opts.check_all()
        try:
            rec = await sirius_sdk.NonSecrets.get_wallet_record(
                type_=self._storage_type, id_=uri, options=opts
            )
        except:
            rec = None
        if rec is None:
            recs, _ = await sirius_sdk.NonSecrets.wallet_search(
                type_=self._storage_type, query={self.ATTR_URN: uri}, options=opts, limit=1
            )
            if recs:
                rec = recs[0]
        if rec:
            self.__cached_info = (uri, rec)
        return rec

    @property
    def _storage_type(self) -> str:
        my_id = self.cfg.id or self.cfg.reference_id
        return f'{self.STORAGE_TYPE}:{my_id}'

    @staticmethod
    def __normalize_uri(uri: str):
        p = urlparse(uri)
        path = os.path.join(p.netloc, p.path)
        while path.startswith('/'):
            path = path[1:]
        return os.path.join('file:///', path)

    def __clean_income_attributes(self, **attributes) -> dict:
        return {k: v for k, v in attributes.items() if k not in self.RESERVED_ATTRIBS}

    @staticmethod
    def __extract_meta_from_info(info: dict) -> dict:
        meta = {}
        if info and 'value' in info:
            try:
                meta = json.loads(info['value'])
            except json.JSONDecodeError:
                pass
        return meta

    def __extract_attributed_from_info(self, info: dict) -> dict:
        tags = info.get('tags', {})
        return {k: v for k, v in tags.items() if k not in self.RESERVED_ATTRIBS}

    def __check_is_open(self):
        if not self.__is_open:
            raise DataVaultStateError('You should open Vault at first!')

    async def __load_storage_encryption(self, storage_id: str) -> Optional[StreamEncryption]:
        storage_type = f'{self._storage_type}/storage'
        opts = sirius_sdk.NonSecretsRetrieveRecordOptions(retrieve_value=True)
        try:
            rec = await sirius_sdk.NonSecrets.get_wallet_record(
                type_=storage_type, id_=storage_id, options=opts
            )
            js = json.loads(rec['value'])
            cek = sirius_sdk.encryption.b58_to_bytes(js['cek'])
            jwe = js['jwe']
            enc = StreamEncryption.from_jwe(jwe, cek)
            return enc
        except:
            return None

    async def __init_storage_encryption(self, storage_id: str, enc: StreamEncryption):
        storage_type = f'{self._storage_type}/storage'
        if enc.cek is None:
            raise EncryptionError('CEK is empty while storage initialization')
        try:
            js = {'cek': sirius_sdk.encryption.bytes_to_b58(enc.cek), 'jwe': enc.jwe.as_json()}
            await sirius_sdk.NonSecrets.add_wallet_record(
                type_=storage_type, id_=storage_id, value=json.dumps(js)
            )
        except:
            raise DataVaultStateError('Error while initialize storage encryption')

    async def __create_resource(self, uri: str, is_stream: bool, meta: dict = None, chunk_size: int = None, **attributes):
        self.auth.validate(can_create=True)
        storage = await self._mounted()
        info = await self.__load_resource_info(uri)
        if await storage.exists(uri):
            raise DataVaultCreateResourceError(f'Resource with uri: "{uri}" already exists')
        if info is not None:
            await self.__remove_resource(uri, only_infos=True)
        meta = meta or {}
        if self.META_CREATED_ATTR not in meta:
            meta[self.META_CREATED_ATTR] = datetime.datetime.utcnow().isoformat(sep=' ') + 'Z'
        tags = self.__clean_income_attributes(**attributes)
        tags.update(
            {
                self.ATTR_IS_STREAM: 'yes' if is_stream is True else 'no',
                self.ATTR_CHUNK_SIZE: chunk_size or 'null',
                self.ATTR_CHUNKS_NUM: '0',
                self.ATTR_URN: 'urn:uuid:' + uuid.uuid4().hex
            }
        )
        if is_stream is True:
            tags[self.ATTR_CHUNKS_NUM] = '0'
        await sirius_sdk.NonSecrets.add_wallet_record(
            type_=self._storage_type, id_=uri, value=json.dumps(meta), tags=tags
        )
        try:
            await storage.create(uri)
        except BaseConfidentialStorageError:
            await sirius_sdk.NonSecrets.delete_wallet_record(type_=self._storage_type, id_=uri)
            raise

    async def __remove_resource(self, uri: str, only_infos: bool = True):
        self.auth.validate(can_create=True)
        if only_infos is False:
            storage = await self._mounted()
            await storage.remove(uri)
        info = await self.__load_resource_info(uri)
        if info:
            await sirius_sdk.NonSecrets.delete_wallet_record(type_=self._storage_type, id_=uri)
        self.__clean_caches()

    def __clean_caches(self):
        self.__cached_info = ('', {})
