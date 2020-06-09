class BaseSiriusException(Exception):
    pass


class ConnectionClosed(BaseSiriusException):
    pass


class TimeoutIO(BaseSiriusException):
    pass


class ErrorIO(BaseSiriusException):
    pass


class InvalidPayloadStructure(BaseSiriusException):
    pass


class UnsupportedData(BaseSiriusException):
    pass


class ValueIsEmpty(BaseSiriusException):
    pass


class ExceptionIsEmpty(BaseSiriusException):
    pass


class PromiseTriggered(BaseSiriusException):
    pass


class PromiseContextException(BaseSiriusException):

    def __init__(self, class_name: str, printable: str, *args, **kwargs):
        self.class_name = class_name
        self.printable = printable
        super().__init__(*args, **kwargs)
