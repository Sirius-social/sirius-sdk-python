class BaseSiriusException(Exception):
    pass


class SiriusConnectionClosed(BaseSiriusException):
    pass


class SiriusTimeoutIO(BaseSiriusException):
    pass


class SiriusIOError(BaseSiriusException):
    pass


class SiriusInvalidPayloadStructure(BaseSiriusException):
    pass


class SiriusUnsupportedData(BaseSiriusException):
    pass


class SiriusValueIsEmpty(BaseSiriusException):
    pass


class SiriusExceptionIsEmpty(BaseSiriusException):
    pass


class SiriusPromiseContextException(BaseSiriusException):

    def __init__(self, class_name: str, printable: str, *args, **kwargs):
        self.class_name = class_name
        self.printable = printable
        super().__init__(*args, **kwargs)


class SiriusCryptoError(BaseSiriusException):
    """ Failed crypto call. """
