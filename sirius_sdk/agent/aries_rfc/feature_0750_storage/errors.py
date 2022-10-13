from typing import Union

from sirius_sdk.messaging import Message


class BaseConfidentialStorageError(RuntimeError):

    PROBLEM_CODE = 'confidential_storage_error'

    def __init__(self, message, *args):
        super().__init__(message, *args)

    @property
    def message(self) -> str:
        return self.args[0] if self.args else ''


class ConfidentialStorageUnexpectedMessageType(BaseConfidentialStorageError):

    PROBLEM_CODE = 'invalid_message_type'

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
    PROBLEM_CODE = 'invalid_request'


class StreamEOF(BaseConfidentialStorageError):
    PROBLEM_CODE = 'eof'


class EncryptionError(BaseConfidentialStorageError):
    PROBLEM_CODE = 'encryption_error'


class StreamInitializationError(BaseConfidentialStorageError):
    PROBLEM_CODE = 'initialization_error'


class StreamSeekableError(BaseConfidentialStorageError):
    PROBLEM_CODE = 'stream_is_not_seekable'


class DocumentFormatError(BaseConfidentialStorageError):
    PROBLEM_CODE = 'document_format_error'


class StreamFormatError(BaseConfidentialStorageError):
    PROBLEM_CODE = 'stream_format_error'


class ConfidentialStorageTimeoutOccurred(BaseConfidentialStorageError):
    PROBLEM_CODE = 'timeout_occurred'


class ConfidentialStoragePermissionDenied(BaseConfidentialStorageError):
    PROBLEM_CODE = 'permission_denied'


class DataVaultCreateResourceError(BaseConfidentialStorageError):
    PROBLEM_CODE = 'resource_error'


class DataVaultResourceMissing(BaseConfidentialStorageError):
    PROBLEM_CODE = 'resource_missing'


class DataVaultSessionError(BaseConfidentialStorageError):
    PROBLEM_CODE = 'session_error'


class DataVaultStateError(BaseConfidentialStorageError):
    PROBLEM_CODE = 'state_error'


class DataVaultOSError(BaseConfidentialStorageError):
    PROBLEM_CODE = 'os_error'

    def __init__(self, message: Union[OSError, str], *args):
        if isinstance(message, OSError):
            err_msg = str(message)
            for arg in message.args:
                if isinstance(arg, str):
                    err_msg = arg
                    break
        else:
            err_msg = message
        super().__init__(err_msg, *args)
