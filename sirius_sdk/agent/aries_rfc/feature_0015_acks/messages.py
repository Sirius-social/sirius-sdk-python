import re
import base64
from enum import Enum
from typing import List, Optional

from ....errors.exceptions import *
from ....messaging import Message, Type, check_for_attributes
from ..base import ARIES_DOC_URI


ARIES_PROTOCOL = 'notification'


class Status(Enum):
    # outcome has occurred, and it was positive
    OK = 'OK'

    # no outcome is yet known
    PENDING = 'PENDING'

    # outcome has occurred, and it was negative
    FAIL = 'FAIL'


class AckMessage(Message):
    """0015 Message implementation

    https://github.com/hyperledger/aries-rfcs/tree/master/features/0015-acks
    """

    NAME = 'ack'

    def __init__(self, status: Status, version: str='1.0', *args, **kwargs):
        kwargs['@type'] = Type(
            doc_uri=ARIES_DOC_URI,
            protocol=ARIES_PROTOCOL,
            version=version,
            name=self.NAME
        ).normalized
        kwargs['status'] = status.value
        super().__init__(*args, **kwargs)

    @property
    def status(self) -> Status:
        status = self.get('status', None)
        if status == Status.OK.value:
            return Status.OK
        elif status == Status.PENDING.value:
            return Status.PENDING
        elif status == Status.FAIL.value:
            return Status.FAIL
        else:
            raise RuntimeError('Unexpected status value')

    def validate(self):
        if self.type.protocol != ARIES_PROTOCOL:
            raise SiriusValidationError('Unexpected protocol "%s"' % self.type.protocol)
        if self.type.name != self.NAME:
            raise SiriusValidationError('Unexpected name "%s"' % self.type.name)
        check_for_attributes(
            msg=self,
            expected_attributes=['status']
        )

    @property
    def please_ack(self):
        """https://github.com/hyperledger/aries-rfcs/tree/master/features/0317-please-ack"""
        return self.get('~please_ack', None)
