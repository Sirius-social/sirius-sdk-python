import asyncio
from typing import Any

from ..errors.exceptions import *


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

    class Promise:

        def __init__(self, value_setter: callable, exc_setter: callable, is_triggered: callable):
            self.__value_setter = value_setter
            self.__exc_setter = exc_setter
            self.__is_triggered = is_triggered

        def set_value(self, value: Any):
            self.__value_setter(value)

        def set_exception(self, e: Exception):
            self.__exc_setter(e)

        @property
        def is_triggered(self):
            return self.__is_triggered()

    def __init__(self):
        self.__value = None
        self.__triggered = False
        self.__exception = None
        self.__event = asyncio.Event()
        self.__promise = Future.Promise(self._set_value, self._set_exception, self._is_triggered)

    @property
    def promise(self):
        return self.__promise
        
    async def wait(self, timeout: int=None) -> bool:

        async def __wait():
            await self.__event.wait()

        done, pending = await asyncio.wait([__wait()], timeout=timeout)
        if done:
            return True
        else:
            f = list(pending)[0]
            f.cancel()
            return False

    def get_value(self) -> Any:
        """Get response value.

        :return: value
        :raises:
           - SiriusPendingOperation: response was not received yet. Call walt(0) to safely check value persists.
        """
        if not self.__triggered:
            raise SiriusPendingOperation()
        return self.__value

    def has_exception(self) -> bool:
        """Check if response was interrupted with exception

        :return: True if request have done with exception
        :raises:
           - SiriusPendingOperation: response was not received yet. Call walt(0) to safely check value persists.
        """
        if not self.__triggered:
            raise SiriusPendingOperation()
        return self.__exception is not None

    def raise_exception(self):
        if self.has_exception():
            raise self.__exception
        else:
            raise SiriusValueEmpty()

    def _set_value(self, value: Any):
        if self.__triggered:
            raise SiriusAlreadyTriggered("Future already triggered")
        self.__triggered = True
        self.__value = value
        self.__event.set()

    def _set_exception(self, e: Exception):
        if self.__triggered:
            raise SiriusAlreadyTriggered("Future already triggered")
        self.__triggered = True
        self.__exception = e
        self.__event.set()

    def _is_triggered(self):
        return self.__triggered
