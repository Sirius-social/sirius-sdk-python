class BaseStreamError(RuntimeError):

    def __init__(self, message):
        super().__init__(message)

    @property
    def message(self) -> str:
        return self.args[0] if self.args else ''


class StreamEOF(BaseStreamError):
    pass


class StreamEncryptionError(BaseStreamError):
    pass


class StreamInitializationError(BaseStreamError):
    pass


class StreamSeekableError(BaseStreamError):
    pass


class StreamFormatError(BaseStreamError):
    pass


class StreamTimeoutOccurred(BaseStreamError):
    pass