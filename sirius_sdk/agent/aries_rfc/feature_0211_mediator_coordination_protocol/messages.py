from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage
from typing import List, Union


class CoordinateMediationMessage(AriesProtocolMessage, metaclass=RegisterMessage):
    """Aries feature 0211 Message implementation

    https://github.com/hyperledger/aries-rfcs/blob/master/features/0211-route-coordination
    """

    PROTOCOL = 'coordinate-mediation'


class MediateRequest(CoordinateMediationMessage, metaclass=RegisterMessage):

    NAME = 'mediate-request'


class MediateDeny(CoordinateMediationMessage, metaclass=RegisterMessage):

    NAME = 'mediate-deny'


class MediateGrant(CoordinateMediationMessage, metaclass=RegisterMessage):

    NAME = 'mediate-grant'

    def __init__(self, endpoint: str, routing_keys: List[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['endpoint'] = endpoint
        self['routing_keys'] = routing_keys


class KeylistAddAction(dict):

    def __init__(self, recipient_key: str, result: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['action'] = 'add'
        self['recipient_key'] = recipient_key
        if result is not None:
            self['result'] = result


class KeylistRemoveAction(dict):

    def __init__(self, recipient_key: str, result: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['action'] = 'remove'
        self['recipient_key'] = recipient_key
        if result is not None:
            self['result'] = result


class KeylistUpdate(CoordinateMediationMessage, metaclass=RegisterMessage):

    NAME = 'keylist-update'

    def __init__(self, endpoint: str, updates: List[Union[KeylistAddAction, KeylistRemoveAction]], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['endpoint'] = endpoint
        self['updates'] = updates


class KeylistUpdateResponce(CoordinateMediationMessage, metaclass=RegisterMessage):

    NAME = 'keylist-update-responce'

    def __init__(self, updated: List[Union[KeylistAddAction, KeylistRemoveAction]], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['updated'] = updated


class KeylistQuery(CoordinateMediationMessage, metaclass=RegisterMessage):

    NAME = 'keylist-query'

    def __init__(self, limit: int = None, offset: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if limit is not None and offset is not None:
            self['paginate'] = {}
            self['paginate']['limit'] = limit
            self['paginate']['offset'] = offset


class Keylist(CoordinateMediationMessage, metaclass=RegisterMessage):

    NAME = 'keylist'

    def __init__(self, keys: List[str], count: int = None, offset: int = None, remaining: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self["keys"] = [{"recipient_key": key} for key in keys]
        if count is not None and offset is not None and remaining is not None:
            self['pagination'] = {}
            self['pagination']['count'] = count
            self['pagination']['offset'] = offset
            self['pagination']['remaining'] = remaining
