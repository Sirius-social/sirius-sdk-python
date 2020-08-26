from enum import Enum
from typing import Optional, Union

from sirius_sdk.messaging import check_for_attributes
from sirius_sdk.errors.exceptions import *
from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage, THREAD_DECORATOR


class Status(Enum):
    # outcome has occurred, and it was positive
    OK = 'OK'

    # no outcome is yet known
    PENDING = 'PENDING'

    # outcome has occurred, and it was negative
    FAIL = 'FAIL'


class Ack(AriesProtocolMessage, metaclass=RegisterMessage):

    PROTOCOL = 'notification'
    NAME = 'ack'

    def __init__(self, thread_id: str = None, status: Optional[Union[Status, str]] = None, *args, **kwargs):
        super(Ack, self).__init__(*args, **kwargs)
        if status is not None:
            if isinstance(status, Status):
                self['status'] = status.value
            else:
                self['status'] = status
        if thread_id is not None:
            thread = self.get(THREAD_DECORATOR, {})
            thread['thid'] = thread_id
            self[THREAD_DECORATOR] = thread

    def validate(self):
        super().validate()
        check_for_attributes(self, [THREAD_DECORATOR])
        check_for_attributes(self[THREAD_DECORATOR], ['thid'])

    @property
    def status(self) -> Optional[Status]:
        status = self.get('status', None)
        if status is None:
            return Status.OK
        elif status == Status.OK.value:
            return Status.OK
        elif status == Status.PENDING.value:
            return Status.PENDING
        elif status == Status.FAIL.value:
            return Status.FAIL
        else:
            return None

    @property
    def thread_id(self) -> Optional[str]:
        return self.get(THREAD_DECORATOR, {}).get('thid', None)

    @property
    def please_ack(self) -> Optional[dict]:
        """https://github.com/hyperledger/aries-rfcs/tree/master/features/0317-please-ack"""
        return self.get('~please_ack', None)
