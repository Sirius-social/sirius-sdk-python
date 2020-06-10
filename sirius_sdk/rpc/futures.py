import uuid
import json
import base64
import logging
import datetime

from ..exceptions import *
from ..indy_exceptions import *
from ..base import AddressedTunnel


MSG_TYPE = 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/future'


class Future:

    def __init__(self, tunnel: AddressedTunnel, expiration_time: datetime.datetime=None):
        self.__id = uuid.uuid4().hex
        self._value = None
        self.__read_ok = False
        self.__tunnel = tunnel
        self.__exception = None
        self.__expiration_stamp = expiration_time

    @property
    def promise(self):
        return {
            'id': self.__id,
            'channel_address': self.__tunnel.address,
            'expiration_stamp': self.__expiration_stamp.timestamp() if self.__expiration_stamp else None
        }

    async def wait(self, timeout: int):
        """

        :param timeout: waiting timeout in seconds
        :return: True/False
        """
        if self.__read_ok:
            return True
        try:
            if timeout == 0:
                return False
            if self.__expiration_stamp:
                expires_time = self.__expiration_stamp
            else:
                expires_time = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
            while datetime.datetime.now() < expires_time:
                timedelta = expires_time - datetime.datetime.now()
                timeout = max(timedelta.seconds, 0)
                payload = await self.__tunnel.read(timeout)
                if (payload.get('@type') == MSG_TYPE) and (payload.get('@id') == self.__id):
                    exception = payload['exception']
                    if exception:
                        self.__exception = exception
                    else:
                        value = payload['value']
                        if payload['is_tuple']:
                            self._value = tuple(value)
                        elif payload['is_bytes']:
                            self._value = base64.b64decode(value.encode('ascii'))
                        else:
                            self._value = value
                    self.__read_ok = True
                    return True
                else:
                    logging.warning(
                        'Unexpected payload \n' + json.dumps(payload, indent=2, sort_keys=True) +
                        '\n Expected id: "%s"' % self.__id
                    )
            return False
        except SiriusTimeoutIO:
            return False

    def get_value(self):
        if self.__read_ok is False:
            raise SiriusValueIsEmpty
        return self._value

    def has_exception(self):
        return self.__exception is not None

    @property
    def exception(self):
        if self.has_exception():
            if self.__exception['indy']:
                indy_exc = self.__exception['indy']
                exc_class = errorcode_to_exception(errorcode=indy_exc['error_code'])
                exc = exc_class(
                    error_code=indy_exc['error_code'],
                    error_details=dict(message=indy_exc['message'], indy_backtrace=None)
                )
                return exc
            else:
                return SiriusPromiseContextException(
                    class_name=self.__exception['class_name'], printable=self.__exception['printable']
                )
        else:
            return None

    def raise_exception(self):
        if self.has_exception():
            raise self.exception
        else:
            raise SiriusExceptionIsEmpty()
