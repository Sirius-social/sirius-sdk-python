class BaseSiriusException(Exception):

    def __str__(self):
        return self.__doc__ or super().__str__()


class SiriusConnectionClosed(BaseSiriusException):
    pass


class SiriusTimeoutIO(BaseSiriusException):
    pass


class SiriusRPCError(BaseSiriusException):
    pass


class SiriusTimeoutRPC(SiriusRPCError):
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


class SiriusAlreadyTriggered(BaseSiriusException):
    pass


class SiriusPromiseContextException(BaseSiriusException):

    def __init__(self, class_name: str, printable: str, *args, **kwargs):
        self.class_name = class_name
        self.printable = printable
        super().__init__(*args, **kwargs)


class SiriusCryptoError(BaseSiriusException):
    """ Failed crypto call. """


class SiriusInvalidMessage(BaseSiriusException):
    """ Thrown when message is malformed. """


class SiriusInvalidType(BaseSiriusException):
    """ When type is unparsable or invalid. """


class SiriusValidationError(BaseSiriusException):
    pass


class SiriusInvalidMessageClass(BaseSiriusException):
    pass
