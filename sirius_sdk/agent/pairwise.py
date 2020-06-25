from typing import List


class TheirEndpoint:

    def __init__(self, endpoint: str, verkey: str, routing_keys: List[str]=None):
        self.endpoint = endpoint
        self.verkey = verkey
        self.routing_keys = routing_keys or []


class Pairwise:

    class Their(TheirEndpoint):

        def __init__(self, did: str, label: str, endpoint: str, verkey: str, routing_keys: List[str]=None):
            self.did = did
            self.label = label
            super().__init__(endpoint, verkey, routing_keys)

    class Me:

        def __init__(self, did, verkey):
            self.did = did
            self.verkey = verkey

    def __init__(self, metadata: dict=None):
        self.__their = None
        self.__me = None
        self.__metadata = metadata

    @property
    def their(self) -> Their:
        return self.__their

    @property
    def me(self) -> Me:
        return self.__me

    @property
    def metadata(self) -> dict:
        return self.__metadata
