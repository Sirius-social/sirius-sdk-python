import datetime
import json
from enum import Enum
from dataclasses import dataclass
from collections import UserDict
from typing import List, Optional, Dict, Any, Union

from sirius_sdk.agent.aries_rfc import Ack
from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage, \
    VALID_DOC_URI, AriesProblemReport
from .documents import EncryptedDocument
from .components import StructuredDocument, HMAC, VaultConfig
from .utils import datetime_to_utc_str


class BaseConfidentialStorageMessage(AriesProtocolMessage, metaclass=RegisterMessage):
    """Aries feature 0750 Messages implementation

    """
    DOC_URI = VALID_DOC_URI[0]
    PROTOCOL = 'storage'


class ConfidentialStorageMessageProblemReport(AriesProblemReport, metaclass=RegisterMessage):
    PROTOCOL = BaseConfidentialStorageMessage.PROTOCOL


@dataclass
class StructuredDocumentAttach:
    """A structured document is used to store application data as well as metadata about the application data.
    This information is typically encrypted and then stored on the data vault.
    """

    class Meta(UserDict):
        """Key-value metadata associated with the structured document."""

        def __init(
                self, created: Union[str, datetime.datetime] = None,
                content_type: str = None, chunks: int = None, **kwargs
        ):
            super().__init__(**kwargs)
            if created is not None:
                if isinstance(created, datetime.datetime):
                    self['created'] = datetime_to_utc_str(created)
                else:
                    self['created'] = created
            if content_type is not None:
                self['contentType'] = content_type
            if chunks is not None:
                self['chunks'] = chunks

        @property
        def created(self) -> Optional[str]:
            return self.get('created', None)

        @property
        def content_type(self) -> Optional[str]:
            return self.get('contentType', None)

        @property
        def chunks(self) -> Optional[int]:
            return self.get('chunks', None)

    class Stream(UserDict):
        """The stream identifier MUST be a URI that references a stream on the same data vault.
        Once the stream has been written to the data vault, the content identifier MUST be updated such that
        it is a valid hashlink. To allow for streaming encryption, the value of the digest for the stream is assumed
        to be unknowable until after the stream has been written.
        The hashlink MUST exist as a content hash for the stream that has been written to the data vault."""

        def __init__(self, id_: str = None, **kwargs):
            super().__init__(**kwargs)
            if id_ is not None:
                self['id'] = id_

        @property
        def id(self) -> Optional[str]:
            return self.get('id', None)

    class Indexed(UserDict):

        def __init__(self, sequence: int = None, attributes: List[str] = None, hmac: Union[dict, HMAC] = None, **kwargs):
            super().__init__(**kwargs)
            if sequence is not None:
                self['sequence'] = sequence
            if attributes is not None:
                self['attributes'] = attributes
            if isinstance(hmac, HMAC):
                self['hmac'] = hmac.as_json()
            elif isinstance(hmac, dict):
                self['hmac'] = hmac

        @property
        def sequence(self) -> Optional[int]:
            return self.get('sequence', None)

        @property
        def attributes(self) -> List[str]:
            return self.get('attributes', [])

        @property
        def hmac(self) -> Optional[HMAC]:
            js = self.get('hmac', None)
            if js:
                return HMAC(id=js.get('id', None), type=js.get('type', None))
            else:
                return None

    # An identifier for the structured document.
    # The value is required and MUST be a Base58-encoded 128-bit random value.
    id: Optional[str] = None
    urn: Optional[str] = None
    # A unique counter for the data vault in order to ensure that clients are properly synchronized to the data vault.
    # The value is required and MUST be an unsigned 64-bit number.
    sequence: int = None

    # Key-value metadata associated with the structured document.
    meta: Meta = None

    # Streams can be used to store images, video, backup files, and any other binary data of arbitrary length.
    stream: Stream = None

    # Indexed metadata
    indexed: Optional[List[Indexed]] = None

    # Key-value content for the structured document.
    _content: Optional[Union[dict, str]] = None

    # A JSON Web Encryption or COSE Encrypted value that, if decoded, results in the corresponding StructuredDocument.
    _jwm: Optional[dict] = None

    _cached: Optional[EncryptedDocument] = None

    @staticmethod
    def create_from(src: StructuredDocument, sequence: int) -> "StructuredDocumentAttach":
        inst = StructuredDocumentAttach(id=src.id, sequence=sequence, urn=src.urn)
        if src.indexed:
            inst.indexed = [
                StructuredDocumentAttach.Indexed(
                    sequence=index.sequence or i,
                    attributes=index.attributes,
                    hmac=index.hmac
                )
                for i, index in enumerate(src.indexed)
            ]
        if src.meta:
            inst.meta = StructuredDocumentAttach.Meta(**src.meta)
        if src.stream:
            inst.stream = StructuredDocumentAttach.Stream(id_=src.id)
        if src.content:
            if src.content.encrypted:
                inst._jwm = src.content.jwm
            else:
                inst._content = src.content.content or b''
        return inst

    @property
    def document(self) -> Optional[EncryptedDocument]:
        if self._cached is not None:
            return self._cached
        if self._content is not None:
            doc = EncryptedDocument()
            doc.content = self._content
            self._cached = doc
            return doc
        elif self._jwm is not None:
            recipients = self._jwm.get('recipients', [])
            target_verkeys = []
            for item in recipients:
                target_verkeys.append(item['header']['kid'])
            doc = EncryptedDocument(target_verkeys=target_verkeys)
            doc.content = json.dumps(self._jwm).encode()
            doc.encrypted = True
            self._cached = doc
            return doc
        else:
            return None

    @document.setter
    def document(self, doc: EncryptedDocument):
        self._cached = None
        self._content = None
        self._jwm = None
        if doc.encrypted and isinstance(doc.content, bytes):
            self._jwm = json.loads(doc.content.decode())
        elif isinstance(doc.content, dict):
            self._content = doc.content
        elif isinstance(doc.content, str):
            self._content = {'message': doc.content}

    def as_json(self) -> dict:
        js = {'id': self.urn}
        if self.meta is not None:
            js['meta'] = dict(self.meta)
        if self.stream is not None:
            js['stream'] = dict(self.stream)
        if self.indexed is not None:
            js['indexed'] = [dict(ind) for ind in self.indexed]
        if self._content is not None:
            content_js = {'id': self.id}
            if self._content:
                if isinstance(self._content, bytes):
                    message = self._content.decode()
                elif isinstance(self._content, str) or isinstance(self._content, dict) or isinstance(self._content, list):
                    message = self._content
                else:
                    message = None
                if message is not None:
                    content_js['message'] = message
            js['content'] = content_js
        if self._jwm is not None:
            js['jwm'] = self._jwm
        return js

    def from_json(self, js: dict):
        self._cached = None
        # Id restored from sub-attrs
        self.id = js.get('content', {}).get('id') or js.get('stream', {}).get('id')
        self.urn = js.get('id', None)
        if not self.id:
            self.id = self.urn
        self.sequence = js.get('sequence', None)
        self.meta = self.Meta(**js['meta']) if 'meta' in js else None
        self.stream = self.Stream(**js['stream']) if 'stream' in js else None
        if 'indexed' in js:
            self.indexed = [self.Indexed(**kwargs) for kwargs in js['indexed']]
        else:
            self.indexed = None
        self._jwm = None
        self._content = None
        if 'jwm' in js:
            self._jwm = js['jwm'] if 'jwm' in js else None
        if 'content' in js:
            self._content = js['content'].get('message', None)


class StreamOperation(BaseConfidentialStorageMessage):

    NAME = 'stream-operation'

    class OperationCode(Enum):
        OPEN = 'open'
        CLOSE = 'close'
        SEEK_TO_CHUNK = 'seek_to_chunk'
        READ_CHUNK = 'read_chunk'
        WRITE_CHUNK = 'write_chunk'
        TRUNCATE = 'truncate'

    def __init__(self, operation: Union[str, OperationCode] = None, params=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if isinstance(operation, self.OperationCode):
            self['operation'] = operation.value
        else:
            self['operation'] = operation
        if params:
            self['params'] = params

    @property
    def operation(self) -> Optional[OperationCode]:
        op = self.get('operation')
        for item in self.OperationCode:
            if op == item.value:
                return item
        return None

    @property
    def params(self) -> Optional[Dict]:
        return self.get('params', None)


class StreamOperationResult(BaseConfidentialStorageMessage):

    NAME = 'stream-operation-result'

    def __init__(self, operation: Union[str, StreamOperation.OperationCode] = None, params=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if isinstance(operation, StreamOperation.OperationCode):
            self['operation'] = operation.value
        else:
            self['operation'] = operation
        if params:
            self['params'] = params

    @property
    def params(self) -> Optional[Dict]:
        return self.get('params', None)


class BaseDataVaultOperation(BaseConfidentialStorageMessage):

    def __init__(
            self, uri: str = None, meta: dict = None, attributes: dict = None,
            chunk_size: int = None, vault: str = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if uri:
            self['uri'] = uri
        if meta:
            self['meta'] = meta
        if attributes:
            self['attributes'] = attributes
        if chunk_size is not None:
            self['chunk_size'] = chunk_size
        if vault is not None:
            self['vault'] = vault

    @property
    def uri(self) -> Optional[str]:
        return self.get('uri', None)

    @property
    def meta(self) -> Optional[dict]:
        return self.get('meta', None)

    @property
    def attributes(self) -> Optional[dict]:
        return self.get('attributes', None)

    @property
    def chunk_size(self) -> Optional[int]:
        return self.get('chunk_size', None)

    @property
    def vault(self) -> Optional[str]:
        return self.get('vault', None)


class DataVaultQueryList(BaseDataVaultOperation):
    NAME = 'vault-query'


class DataVaultResponseList(BaseDataVaultOperation):
    NAME = 'vault-response'

    def __init__(self, vaults: Union[List[VaultConfig], List[dict]] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if vaults is not None and isinstance(vaults, list):
            collection = []
            for cfg in vaults:
                if isinstance(cfg, VaultConfig):
                    collection.append(cfg.as_json())
                elif isinstance(cfg, dict):
                    collection.append(cfg)
            self['vaults'] = collection

    @property
    def vaults(self) -> List[VaultConfig]:
        collection = [VaultConfig.create_from_json(js) for js in self.get('vaults', [])]
        return collection


class DataVaultOpen(BaseDataVaultOperation):
    NAME = 'vault-open'


class DataVaultClose(BaseDataVaultOperation):
    NAME = 'vault-close'


class DataVaultCreateStream(BaseDataVaultOperation):
    NAME = 'vault-create-stream'


class DataVaultCreateDocument(BaseDataVaultOperation):
    NAME = 'vault-create-document'


class DataVaultUpdateResource(BaseDataVaultOperation):
    NAME = 'data-vault-update-resource'


class DataVaultLoadResource(BaseDataVaultOperation):
    NAME = 'data-vault-load-resource'


class DataVaultRemoveResource(BaseDataVaultOperation):
    NAME = 'data-vault-remove-resource'


class DataVaultList(BaseDataVaultOperation):
    NAME = 'data-vault-list'

    def __init__(self, filters: dict = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if filters is not None:
            self['filters'] = filters

    @property
    def filters(self) -> dict:
        return self.get('filters', {})


class DataVaultBindStreamForReading(BaseDataVaultOperation):
    NAME = 'data-vault-bind-stream-reading'

    def __init__(self, uri: str, co_binding_id: str = None, *args, **kwargs):
        super().__init__(uri=uri, *args, **kwargs)
        if co_binding_id is not None:
            self['co_binding_id'] = co_binding_id

    @property
    def co_binding_id(self) -> Optional[str]:
        return self.get('co_binding_id', None)


class DataVaultBindStreamForWriting(BaseDataVaultOperation):
    NAME = 'data-vault-bind-stream-writing'

    def __init__(self, uri: str, co_binding_id: str = None, *args, **kwargs):
        super().__init__(uri=uri, *args, **kwargs)
        if co_binding_id is not None:
            self['co_binding_id'] = co_binding_id

    @property
    def co_binding_id(self) -> Optional[str]:
        return self.get('co_binding_id', None)


class DataVaultSaveDocument(BaseDataVaultOperation):
    NAME = 'data-vault-save-document'

    @property
    def document(self) -> Optional[EncryptedDocument]:
        attachment = self.get('~attach', [])
        if isinstance(attachment, list):
            attachment = attachment[0]
        if 'content' in attachment:
            content = attachment['content']
            if 'message' in content:
                return EncryptedDocument(content=content['message'])
            else:
                return EncryptedDocument(content=content)
        elif 'jwm' in attachment:
            jwm = attachment['jwm']
            doc = EncryptedDocument(content=json.dumps(jwm).encode())
            doc.encrypted = True
            return doc
        else:
            return None

    @document.setter
    def document(self, value: EncryptedDocument):
        if value.encrypted:
            if isinstance(value.content, bytes):
                jwm = json.loads(value.content.decode())
            elif isinstance(value.content, str):
                jwm = json.loads(value.content)
            else:
                jwm = value.content
            self['~attach'] = {
                'jwm': jwm
            }
        else:
            if isinstance(value.content, bytes):
                content = value.content.decode()
            else:
                content = value.content
            if isinstance(content, str):
                self['~attach'] = {
                    'content': {'message': content}
                }
            else:
                self['~attach'] = {
                    'content': content
                }


class DataVaultOperationAck(Ack):
    PROTOCOL = BaseDataVaultOperation.PROTOCOL


class StructuredDocumentMessage(BaseConfidentialStorageMessage):
    NAME = 'structured-documents'

    def __init__(self, documents: List[StructuredDocumentAttach] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if documents is not None:
            attach = []
            for i, doc in enumerate(documents):
                attach.append({'@id': f'doc-{i}', 'data': doc.as_json()})
            self['doc~attach'] = attach

    @property
    def documents(self) -> List[StructuredDocumentAttach]:
        collection = []
        doc_attachments = self.get('doc~attach', {})
        if isinstance(doc_attachments, dict):
            doc_attachments = [doc_attachments]
        for attach in doc_attachments:
            doc = StructuredDocumentAttach()
            doc.from_json(attach['data'])
            collection.append(doc)
        return collection
