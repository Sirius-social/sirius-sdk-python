import json
import os.path

from typing import List, Optional

import sirius_sdk
from sirius_sdk.agent.aries_rfc.feature_0750_storage import EncryptedDataVault, StructuredDocument, \
    ConfidentialStorageAuthProvider, VaultConfig, ConfidentialStorageRawByteStorage, FileSystemRawByteStorage, \
    StreamEncryption, AbstractWriteOnlyStream, AbstractReadOnlyStream, EncryptedDocument
from sirius_sdk.agent.aries_rfc.feature_0750_storage.errors import StreamEncryptionError, DataVaultCreateResourceError, \
    BaseConfidentialStorageError, DataVaultCreateResourceMissing, StreamInitializationError
from sirius_sdk.agent.aries_rfc.feature_0750_storage.encoding import ConfidentialStorageEncType
from sirius_sdk.agent.aries_rfc.feature_0750_storage.impl.file_system import FileSystemWriteOnlyStream


class SimpleDataVault(EncryptedDataVault):

    STORAGE_TYPE = 'data_vault'

    class SimpleDataVaultIndexes(EncryptedDataVault.Indexes):

        def __init__(self, storage: ConfidentialStorageRawByteStorage):
            self.__storage = storage

        async def filter(self, **attributes) -> List[StructuredDocument]:
            pass

    def __init__(self, mounted_dir: str, auth: ConfidentialStorageAuthProvider, cfg: VaultConfig = None):
        if not os.path.isdir(mounted_dir):
            raise RuntimeError(f'Directory "{mounted_dir}" does not exists')
        super().__init__(auth, cfg)
        self.__mounted_dir = os.path.join(mounted_dir, f'vault_{auth.entity.their.did}')
        if not os.path.isdir(self.__mounted_dir):
            os.mkdir(self.__mounted_dir)
        self.__storage: Optional[ConfidentialStorageRawByteStorage] = None
        self.__indexes: Optional[SimpleDataVault.SimpleDataVaultIndexes]  = None

    async def indexes(self) -> EncryptedDataVault.Indexes:
        storage = await self._mounted()
        indexes = SimpleDataVault.SimpleDataVaultIndexes(storage)
        return indexes

    async def create_stream(self, uri: str, meta: dict = None, chunk_size: int = None, **attributes):
        await self.__create_resource(uri, is_stream=True, meta=meta, chunk_size=chunk_size, **attributes)

    async def create_document(self, uri: str, meta: dict = None, **attributes):
        await self.__create_resource(uri, is_stream=False, meta=meta, **attributes)

    async def update(self, uri: str, meta: dict = None, **attributes):
        pass

    async def load(self, uri: str) -> EncryptedDocument:
        info = await self.__load_resource_info(uri)
        if info is None:
            raise DataVaultCreateResourceMissing(f'Mission resource uri: {uri}')
        if info['tags']['is_stream'] != 'no':
            raise StreamInitializationError(f'Resource uri: "{uri}" is stream, you can not operate as document with it')
        chunks_num = int(info['tags'].get('chunks_num', '0'))
        storage = await self._mounted()
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
            except:
                pass
            return doc
        finally:
            await stream.close()

    async def save(self, uri: str, doc: EncryptedDocument):
        info = await self.__load_resource_info(uri)
        if info is None:
            raise DataVaultCreateResourceMissing(f'Mission resource uri: {uri}')
        if info['tags']['is_stream'] != 'no':
            raise StreamInitializationError(f'Resource uri: "{uri}" is stream, you can not operate as document with it')
        tags = info['tags']
        storage = await self._mounted()
        stream = await storage.writeable(uri)
        await stream.open()
        try:
            await doc.save(stream)
            tags.update({'chunks_num': str(stream.chunks_num)})
            await sirius_sdk.NonSecrets.update_wallet_record_tags(
                type_=self.STORAGE_TYPE, id_=uri, tags=tags
            )
        finally:
            await stream.close()

    async def readable(self, uri: str) -> AbstractReadOnlyStream:
        info = await self.__load_resource_info(uri)
        if info is None:
            raise DataVaultCreateResourceMissing(f'Mission resource uri: {uri}')
        if info['tags']['is_stream'] != 'yes':
            raise StreamInitializationError(f'Resource uri: "{uri}" is not stream')
        chunks_num = int(info['tags'].get('chunks_num', '0'))
        storage = await self._mounted()
        stream = await storage.readable(uri, chunks_num)
        return stream

    async def writable(self, uri: str) -> AbstractWriteOnlyStream:
        info = await self.__load_resource_info(uri)
        if info is None:
            raise DataVaultCreateResourceMissing(f'Mission resource uri: {uri}')
        if info['tags']['is_stream'] != 'yes':
            raise StreamInitializationError(f'Resource uri: "{uri}" is not stream')
        storage = await self._mounted()
        stream = await storage.writeable(uri)
        stored_chunk_size = info['tags'].get('chunk_size', 'null')
        if stored_chunk_size != 'null':
            stream.chunk_size = int(stored_chunk_size)
        if isinstance(stream, FileSystemWriteOnlyStream):

            async def __on_close__(uri_: str, tags_: dict, s_: AbstractWriteOnlyStream):
                tags_.update({'chunks_num': str(s_.chunks_num)})
                await sirius_sdk.NonSecrets.update_wallet_record_tags(
                    type_=self.STORAGE_TYPE, id_=uri_, tags=tags_
                )

            stream.on_closed = __on_close__(uri, info['tags'], stream)
        return stream

    async def _mounted(self) -> ConfidentialStorageRawByteStorage:
        if self.__storage is None:
            if self.cfg.key_agreement is None:
                encryption = None
            else:
                if not self.cfg.key_agreement.type.startswith('X25519'):
                    raise StreamEncryptionError(f'Unsupported key agreement type: "{self.cfg.key_agreement.type}"')
                encryption = StreamEncryption(type_=ConfidentialStorageEncType.X25519KeyAgreementKey2019)
                if self.cfg.key_agreement.id.startswith('did:key:'):
                    target_verkey = self.cfg.key_agreement.id.split(':')[-1]
                else:
                    target_verkey = self.cfg.key_agreement.id
                encryption.setup(target_verkeys=[target_verkey])
            self.__storage = FileSystemRawByteStorage(
                permissions=self.auth.has_permissions(), encryption=encryption
            )
            await self.__storage.mount(self.__mounted_dir)
        return self.__storage

    async def __load_resource_info(self, uri: str) -> Optional[dict]:
        opts = sirius_sdk.NonSecretsRetrieveRecordOptions()
        opts.check_all()
        try:
            rec = await sirius_sdk.NonSecrets.get_wallet_record(
                type_=self.STORAGE_TYPE, id_=uri, options=opts
            )
        except:
            rec = None
        return rec

    async def __create_resource(self, uri: str, is_stream: bool, meta: dict = None, chunk_size: int = None, **attributes):
        info = await self.__load_resource_info(uri)
        if info is not None:
            raise DataVaultCreateResourceError(f'Resource with uri: "{uri}" already exists')
        meta = meta or {}
        tags = dict(**attributes)
        tags.update(dict(is_stream='yes' if is_stream is True else 'no', chunk_size=chunk_size or 'null', chunks_num='0'))
        await sirius_sdk.NonSecrets.add_wallet_record(
            type_=self.STORAGE_TYPE, id_=uri, value=json.dumps(meta), tags=tags
        )
        try:
            storage = await self._mounted()
            await storage.create(uri)
        except BaseConfidentialStorageError:
            await sirius_sdk.NonSecrets.delete_wallet_record(type_=self.STORAGE_TYPE, id_=uri)
            raise
