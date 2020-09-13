from typing import Optional

from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage, THREAD_DECORATOR


class Ping(AriesProtocolMessage, metaclass=RegisterMessage):
    """Implementation of Ping part for trust_ping protocol

    https://github.com/hyperledger/aries-rfcs/tree/master/features/0048-trust-ping
    """

    PROTOCOL = 'trust_ping'
    NAME = 'ping'

    def __init__(self, comment: Optional[str]=None, response_requested: Optional[bool]=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if comment is not None:
            self['comment'] = comment
        if response_requested is not None:
            self['response_requested'] = response_requested

    @property
    def comment(self) -> Optional[str]:
        return self.get('comment', None)

    @property
    def response_requested(self) -> Optional[bool]:
        return self.get('response_requested', None)

    @response_requested.setter
    def response_requested(self, value: bool):
        if value is True:
            self['response_requested'] = True
        else:
            self['response_requested'] = False


class Pong(AriesProtocolMessage, metaclass=RegisterMessage):
    """Implementation of Pong part for trust_ping protocol

    https://github.com/hyperledger/aries-rfcs/tree/master/features/0048-trust-ping
    """

    PROTOCOL = 'trust_ping'
    NAME = 'ping_response'

    def __init__(self, ping_id: str=None, comment: Optional[str]=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if ping_id is not None:
            self.get(THREAD_DECORATOR, {}).update({'thid': ping_id})
        if comment is not None:
            self['comment'] = comment

    @property
    def comment(self) -> Optional[str]:
        return self.get('comment', None)

    @property
    def ping_id(self):
        return self.get(THREAD_DECORATOR, {}).get('thid', None)
