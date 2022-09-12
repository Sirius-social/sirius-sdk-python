from typing import Union

from sirius_sdk.messaging import Message


class BaseConfidentialStorageError(RuntimeError):

    def __init__(self, message, *args):
        super().__init__(message, *args)

    @property
    def message(self) -> str:
        return self.args[0] if self.args else ''


class ConfidentialStorageUnexpectedMessageType(BaseConfidentialStorageError):

    def __init__(self, message: Union[str, Message], *args, **kwargs):
        if isinstance(message, Message):
            if '@type' in message:
                typ = message.get('@type')
                err_msg = f'Unexpected message type: "{typ}"'
            else:
                err_msg = f'Unexpected message type of type: "{message.__class__.__name__}"'
            super().__init__(err_msg)
        else:
            super().__init__(message)


class ConfidentialStorageInvalidRequest(BaseConfidentialStorageError):
    pass


class StreamEOF(BaseConfidentialStorageError):
    pass


class EncryptionError(BaseConfidentialStorageError):
    pass


class StreamInitializationError(BaseConfidentialStorageError):
    pass


class StreamSeekableError(BaseConfidentialStorageError):
    pass


class DocumentFormatError(BaseConfidentialStorageError):
    pass


class StreamFormatError(BaseConfidentialStorageError):
    pass


class ConfidentialStorageTimeoutOccurred(BaseConfidentialStorageError):
    pass


class ConfidentialStoragePermissionDenied(BaseConfidentialStorageError):
    pass


class DataVaultCreateResourceError(BaseConfidentialStorageError):
    pass


class DataVaultResourceMissing(BaseConfidentialStorageError):
    pass


class DataVaultSessionError(BaseConfidentialStorageError):
    pass


class DataVaultStateError(BaseConfidentialStorageError):
    pass
