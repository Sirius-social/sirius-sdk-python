import uuid
import json
import base64
import logging
import datetime
from typing import Any, Optional

from sirius_sdk.errors.exceptions import *
from sirius_sdk.errors.indy_exceptions import *
from sirius_sdk.rpc.tunnel import AddressedTunnel

MSG_TYPE = 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/future'


class Future:
    """Futures and Promises pattern.
    (http://dist-prog-book.com/chapter/2/futures.html)


    Server point has internal communication schemas and communication addresses for
    Aries super-protocol/sub-protocol behaviour
    (https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0003-protocols).

    Future hide communication addresses specifics of server-side service (cloud agent) and pairwise configuration
    of communication between sdk-side and agent-side logic, allowing to take attention on
    response awaiting routines.
    """

    def __init__(self, tunnel: AddressedTunnel, expiration_time: datetime.datetime = None):
        """
        :param tunnel: communication tunnel for server-side cloud agent
        :param expiration_time: time of response expiration
        """
        self.__id = uuid.uuid4().hex
        self._value = None
        self.__read_ok = False
        self.__tunnel = tunnel
        self.__exception = None
        self.expiration_time = expiration_time

    @property
    def promise(self):
        """
        Promise info builder

        :return: serialized promise dump
        """
        return {
            'id': self.__id,
            'channel_address': self.__tunnel.address,
            'expiration_stamp': self.expiration_time.timestamp() if self.expiration_time else None
        }

    async def wait(self, timeout: int=None) -> bool:
        """Wait for response

        :param timeout: waiting timeout in seconds
        :return: True/False
        """
        if self.__read_ok:
            return True
        try:
            if timeout == 0:
                return False
            if self.expiration_time:
                expires_time = self.expiration_time
            elif timeout:
                expires_time = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
            else:
                expires_time = datetime.datetime.now() + datetime.timedelta(days=365)
            while datetime.datetime.now() < expires_time:
                timedelta = expires_time - datetime.datetime.now()
                timeout = max(timedelta.seconds, 0)
                payload = await self.__tunnel.receive(timeout)
                if (payload.get('@type') == MSG_TYPE) and (payload.get('~thread', {}).get('thid', None) == self.__id):
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

    def get_value(self) -> Any:
        """Get response value.

        :return: value
        :raises:
           - SiriusPendingOperation: response was not received yet. Call walt(0) to safely check value persists.
        """
        if self.__read_ok is False:
            raise SiriusPendingOperation()
        return self._value

    def has_exception(self) -> bool:
        """Check if response was interrupted with exception

        :return: True if request have done with exception
        :raises:
           - SiriusPendingOperation: response was not received yet. Call walt(0) to safely check value persists.
        """
        if self.__read_ok is False:
            raise SiriusPendingOperation()
        return self.__exception is not None

    @property
    def exception(self) -> Optional[Exception]:
        """Get exception that have interrupted response routine on server-side.

        :return: Exception instance or None if it does not exists
        """
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
        """Raise exception if exists

        :raises:
           - SiriusValueEmpty: raises if exception is empty
        """
        if self.has_exception():
            raise self.exception
        else:
            raise SiriusValueEmpty()
