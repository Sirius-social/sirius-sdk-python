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
                    utc = created.astimezone(datetime.timezone.utc)
                    self['created'] = utc.isoformat(sep=' ') + 'Z'
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

        def __init__(self, sequence: int = None, attributes: List[str] = None, **kwargs):
            super().__init__(**kwargs)
            if sequence is not None:
                self['sequence'] = sequence
            if attributes is not None:
                self['attributes'] = attributes

        @property
        def sequence(self) -> Optional[int]:
            return self.get('sequence', None)

        @property
        def attributes(self) -> List[str]:
            return self.get('attributes', [])

    # An identifier for the structured document.
    # The value is required and MUST be a Base58-encoded 128-bit random value.
    id: Optional[str] = None
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
    _jwe: Optional[dict] = None

    _cached: Optional[EncryptedDocument] = None

    @property
    def document(self) -> EncryptedDocument:
        if self._cached is not None:
            return self._cached
        if self._content is not None:
            doc = EncryptedDocument()
            doc.content = self._content
            self._cached = doc
            return doc
        elif self._jwe is not None:
            recipients = self._jwe.get('recipients', [])
            target_verkeys = []
            for item in recipients:
                target_verkeys.append(item['header']['kid'])
            doc = EncryptedDocument(target_verkeys=target_verkeys)
            doc.content = json.dumps(self._jwe).encode()
            doc.encrypted = True
            self._cached = doc
            return doc

    @document.setter
    def document(self, doc: EncryptedDocument):
        self._content = None
        self._jwe = None
        if doc.encrypted and isinstance(doc.content, bytes):
            self._jwe = json.loads(doc.content.decode())
        elif isinstance(doc.content, dict):
            self._content = doc.content
        elif isinstance(doc.content, str):
            self._content = {'message': doc.content}

    def as_json(self) -> dict:
        js = {'id': self.id}
        if self.meta is not None:
            js['meta'] = self.meta
        if self.stream is not None:
            js['stream'] = self.stream
        if self.indexed is not None:
            js['indexed'] = self.indexed
        if self._content is not None:
            js['content'] = self._content
        if self._jwe is not None:
            js['jwe'] = self._jwe
        return js

    def from_json(self, js: dict):
        self._cached = None
        self.id = js.get('id', None)
        self.sequence = js.get('sequence', None)
        self.meta = self.Meta(**js['meta']) if 'meta' in js else None
        self.stream = self.Stream(**js['stream']) if 'stream' in js else None
        if 'indexed' in js:
            self.indexed = [self.Indexed(**kwargs) for kwargs in js['indexed']]
        else:
            self.indexed = None
        self._jwe = js['jwe'] if 'jwe' in js else None
        self._content = js['content'] if 'content' in js else None


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


class BaseDataVaultResourceOperation(BaseConfidentialStorageMessage):

    def __init__(self, uri: str, meta: dict = None, attributes: dict = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if uri:
            self['uri'] = uri
        if meta:
            self['meta'] = meta
        if attributes:
            self['attributes'] = attributes

    def uri(self) -> Optional[str]:
        return self.get('uri', None)

    def meta(self) -> Optional[dict]:
        return self.get('meta', None)

    def attributes(self) -> Optional[dict]:
        return self.get('attributes', None)


class DataVaultCreateStream(BaseDataVaultResourceOperation):
    NAME = 'vault-create-stream'


class DataVaultCreateDocument(BaseDataVaultResourceOperation):
    NAME = 'vault-create-document'


class DataVaultUpdateResource(BaseDataVaultResourceOperation):
    NAME = 'data-vault-update-resource'


class DataVaultOperationAck(Ack):
    PROTOCOL = BaseDataVaultResourceOperation.PROTOCOL


class StructuredDocumentMessage(BaseConfidentialStorageMessage):
    NAME = 'structured-documents'

    def __init__(self, documents: List[StructuredDocumentAttach] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if documents is not None:
            attach = []
            for i, doc in enumerate(documents):
                attach.append({'@id': f'doc-{i}', 'data': doc.as_json()})
            self['doc~attach'] = documents

    @property
    def documents(self) -> List[StructuredDocumentAttach]:
        collection = []
        for attach in self.get('doc~attach', []):
            doc = StructuredDocumentAttach()
            doc.from_json(attach['data'])
            collection.append(doc)
        return collection
