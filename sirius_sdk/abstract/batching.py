from typing import Union, List, Optional


class RoutingBatch(dict):

    def __init__(
            self, their_vk: Union[List[str], str], endpoint: str,
            my_vk: Optional[str] = None, routing_keys: Optional[List[str]] = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if isinstance(their_vk, str):
            self['recipient_verkeys'] = [their_vk]
        else:
            self['recipient_verkeys'] = their_vk
        self['endpoint_address'] = endpoint
        self['sender_verkey'] = my_vk
        self['routing_keys'] = routing_keys or []
