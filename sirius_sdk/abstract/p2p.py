from typing import List, Optional
from urllib.parse import urlparse, urlunparse


class Endpoint:
    """Active Agent endpoints
    https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0094-cross-domain-messaging
    """

    def __init__(self, address: str, routing_keys: List[str], is_default: bool=False):
        self.__url = address
        self.__routing_keys = routing_keys
        self.__is_default = is_default

    @property
    def address(self):
        return self.__url

    @property
    def routing_keys(self) -> List[str]:
        return self.__routing_keys

    @property
    def is_default(self):
        return self.__is_default


class TheirEndpoint:

    def __init__(self, endpoint: str, verkey: str, routing_keys: List[str]=None):
        self.endpoint = endpoint
        self.verkey = verkey
        self.routing_keys = routing_keys or []

    @property
    def address(self) -> str:
        return self.endpoint

    @property
    def netloc(self) -> Optional[str]:
        if self.endpoint:
            return urlparse(self.endpoint).netloc
        else:
            return None

    @netloc.setter
    def netloc(self, value: str):
        if self.endpoint:
            components = list(urlparse(self.endpoint))
            components[1] = value
            self.endpoint = urlunparse(components)


class Pairwise:

    class Their(TheirEndpoint):

        def __init__(
                self, did: str, label: str, endpoint: str, verkey: str,
                routing_keys: List[str] = None, did_doc: dict = None
        ):
            self.did = did
            self.label = label
            self.did_doc = did_doc
            super().__init__(endpoint, verkey, routing_keys)

    class Me:

        def __init__(self, did, verkey, did_doc: dict = None):
            self.did = did
            self.verkey = verkey
            self.did_doc = did_doc

        def __eq__(self, other):
            if isinstance(other, Pairwise.Me):
                return self.did == other.did and self.verkey == other.verkey and self.did_doc == other.did_doc

    def __init__(self, me: Me, their: Their, metadata: dict=None):
        self.__me = me
        self.__their = their
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