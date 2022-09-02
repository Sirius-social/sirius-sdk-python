class BaseConfidentialStorageError(RuntimeError):

    def __init__(self, message):
        super().__init__(message)

    @property
    def message(self) -> str:
        return self.args[0] if self.args else ''


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


class DataVaultCreateResourceMissing(BaseConfidentialStorageError):
    pass
