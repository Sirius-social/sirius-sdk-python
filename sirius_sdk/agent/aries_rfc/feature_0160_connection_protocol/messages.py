r"""https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
"""
import re
import base64
from typing import List, Optional

from ....errors.exceptions import *
from ....messaging import Message, Type
from ..base import ARIES_DOC_URI


ARIES_PROTOCOL = 'connection'


class InvitationMessage(Message):
    """0160 Message implementation

    https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
    """

    NAME = 'invitation'

    def __init__(
            self, label: str, recipient_keys: List[str], endpoint: str,
            routing_keys: Optional[List[str]]=None, version: str='1.0', *args, **kwargs
    ):
        kwargs['@type'] = Type(
            doc_uri=ARIES_DOC_URI,
            protocol=ARIES_PROTOCOL,
            version=version,
            name=self.NAME
        ).normalized
        kwargs['label'] = label
        kwargs['recipientKeys'] = recipient_keys
        kwargs['serviceEndpoint'] = endpoint
        kwargs['routingKeys'] = routing_keys or []
        super().__init__(*args, **kwargs)

    @classmethod
    def from_invitation_url(cls, url: str) -> Message:
        matches = re.match("(.+)?c_i=(.+)", url)
        if not matches:
            raise SiriusInvalidMessage("Invite string is improperly formatted")
        msg = Message.deserialize(base64.urlsafe_b64decode(matches.group(2)).decode('utf-8'))
        if msg.type.protocol != ARIES_PROTOCOL:
            raise SiriusInvalidMessage('Unexpected protocol "%s"' % msg.type.protocol)
        if msg.type.name != cls.NAME:
            raise SiriusInvalidMessage('Unexpected protocol name "%s"' % msg.type.name)
        label = msg.pop('label', defaul=None)
        if label is None:
            raise SiriusInvalidMessage('label attribute missing')
        recipient_keys = msg.pop('recipientKeys', default=None)
        if recipient_keys is None:
            raise SiriusInvalidMessage('recipientKeys attribute missing')
        endpoint = msg.pop('serviceEndpoint', default=None)
        if endpoint is None:
            raise SiriusInvalidMessage('serviceEndpoint attribute missing')
        routing_keys = msg.pop('routingKeys', default=[])
        return InvitationMessage(label, recipient_keys, endpoint, routing_keys, **msg)

    @property
    def invitation_url(self):
        b64_invite = base64.urlsafe_b64encode(self.serialize()).decode('ascii')
        return '?c_i=' + b64_invite

    @property
    def label(self) -> str:
        return self.get('label', None)

    @property
    def recipient_keys(self) -> List[str]:
        return self.get('recipientKeys', [])

    @property
    def endpoint(self) -> str:
        return self.get('serviceEndpoint', None)

    @property
    def routing_keys(self) -> List[str]:
        return self.get('routingKeys', [])
