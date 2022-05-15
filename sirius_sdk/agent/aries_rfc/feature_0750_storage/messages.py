from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Union

from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage, THREAD_DECORATOR, \
    VALID_DOC_URI, AriesProblemReport


class BaseConfidentialStorageMessage(AriesProtocolMessage, metaclass=RegisterMessage):
    """Aries feature 0750 Messages implementation

    """
    DOC_URI = VALID_DOC_URI[0]
    PROTOCOL = 'storage'


class ConfidentialStorageMessageProblemReport(AriesProblemReport, metaclass=RegisterMessage):
    PROTOCOL = BaseConfidentialStorageMessage.PROTOCOL


class StorageStructuredDocument(BaseConfidentialStorageMessage):
    """A structured document is used to store application data as well as metadata about the application data.
    This information is typically encrypted and then stored on the data vault.
    """
    NAME = 'structured-document'

    @dataclass
    class Meta:
        created: str = None
        content_type: str = None
        chunks: int = None  # Specifies the number of chunks in the stream
        size: int = None

    def restore_from_json(self, doc: Dict):
        for fld, value in doc.items():
            self[fld] = value

    @dataclass
    class Stream:
        """The stream identifier MUST be a URI that references a stream on the same data vault.
        Once the stream has been written to the data vault, the content identifier MUST be updated such that
        it is a valid hashlink. To allow for streaming encryption, the value of the digest for the stream is assumed
        to be unknowable until after the stream has been written.
        The hashlink MUST exist as a content hash for the stream that has been written to the data vault."""
        id: str


class StreamOperation(BaseConfidentialStorageMessage):

    NAME = 'stream-operation'

    class OperationCode(Enum):
        OPEN = 'open'
        CLOSE = 'close'
        SEEK = 'seek'
        READ = 'read'
        WRITE = 'write'

    def __init__(self, operation: Union[str, OperationCode] = None, params=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if isinstance(operation, self.OperationCode):
            self['operation'] = operation.value
        else:
            self['operation'] = operation
        if params:
            self['params'] = params


class StreamOperationResult(BaseConfidentialStorageMessage):

    NAME = 'stream-operation-result'

    def __init__(self, operation: str = None, params=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['operation'] = operation
        if params:
            self['params'] = params
