import datetime
from typing import Optional

from sirius_sdk.agent.aries_rfc.mixins import ThreadMixin, PleaseAckMixin
from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage


class Message(ThreadMixin, PleaseAckMixin, AriesProtocolMessage, metaclass=RegisterMessage):
    """Implementation of BasicMessage protocol

    https://github.com/hyperledger/aries-rfcs/tree/master/features/0095-basic-message
    """

    PROTOCOL = 'basicmessage'
    NAME = 'message'

    def __init__(self, content: Optional[str] = None, locale: Optional[str] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if locale is not None:
            self['~l10n'] = {"locale": locale}
        if content is not None:
            self['content'] = content

    @property
    def content(self) -> Optional[str]:
        return self.get('content', None)

    @property
    def locale(self) -> Optional[str]:
        return self.get('~l10n', {}).get('locale', None)

    @property
    def sent_time(self) -> Optional[str]:
        return self.get('sent_time', None)

    def set_time(self):
        self['sent_time'] = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
