class BaseSiriusException(Exception):

    def __str__(self):
        return self.__doc__ or super().__str__()


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


class SiriusPendingOperation(BaseSiriusException):
    pass


class SiriusValueEmpty(BaseSiriusException):
    pass


class SiriusPromiseContextException(BaseSiriusException):

    def __init__(self, class_name: str, printable: str, *args, **kwargs):
        self.class_name = class_name
        self.printable = printable
        super().__init__(*args, **kwargs)


class SiriusCryptoError(BaseSiriusException):
    """ Failed crypto call. """
