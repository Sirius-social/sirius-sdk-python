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
