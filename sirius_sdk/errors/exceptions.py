from typing import Any


class BaseSiriusException(Exception):
    
    def __init__(self, message: str=None, *args, **kwargs):
        super(BaseSiriusException, self).__init__(message, *args, **kwargs)
        self.message = message

    @staticmethod
    def _prefix_msg(msg, prefix=None):
        return "{}{}".format(
            "" if prefix is None else "{}: ".format(prefix),
            msg
        )

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


class SiriusContextError(BaseSiriusException):
    pass


class SiriusInitializationError(BaseSiriusException):
    pass


class SiriusInvalidMessageClass(BaseSiriusException):
    pass


class SiriusFieldTypeError(BaseSiriusException, TypeError):
    """Exception for TypeError

    Extends TypeError to provide formatted error message

    :param v_name: variable name
    :param v_value: variable value
    :param v_exp_t: expected variable type
    """

    def __init__(self, v_name: str, v_value: Any, v_exp_t: Any, *args, prefix=None):
        super().__init__(
            self._prefix_msg(
                ("variable '{}', type {}, expected: {}".format(v_name, type(v_value), v_exp_t)),
                prefix
            ), *args
        )


class SiriusFieldValueError(BaseSiriusException, ValueError):
    """Exception for ValueError

    Extends ValueError to provide formatted error message

    :param v_name: variable name
    :param v_value: variable value
    :param v_exp_value: expected variable value
    :param prefix: (optional) prefix for the message
    """
    def __init__(self, v_name: str, v_value: Any, v_exp_value: Any, *args,
                 prefix=None):
        super().__init__(
            self._prefix_msg(
                ("variable '{}', value {}, expected: {}".format(v_name, v_value, v_exp_value)),
                prefix
            ), *args
        )
