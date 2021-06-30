import sys
from abc import ABC, abstractmethod
from typing import List, Optional
from urllib.parse import urlparse, urlunparse

from sirius_sdk.agent.wallet.abstract.did import AbstractDID
from sirius_sdk.agent.wallet.abstract.pairwise import AbstractPairwise


class TheirEndpoint:

    def __init__(self, endpoint: str, verkey: str, routing_keys: List[str]=None):
        self.endpoint = endpoint
        self.verkey = verkey
        self.routing_keys = routing_keys or []

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


class AbstractPairwiseList(ABC):

    @abstractmethod
    async def create(self, pairwise: Pairwise):
        raise NotImplemented

    @abstractmethod
    async def update(self, pairwise: Pairwise):
        raise NotImplemented

    @abstractmethod
    async def is_exists(self, their_did: str) -> bool:
        raise NotImplemented

    @abstractmethod
    async def ensure_exists(self, pairwise: Pairwise):
        raise NotImplemented

    @abstractmethod
    async def load_for_did(self, their_did: str) -> Optional[Pairwise]:
        raise NotImplemented

    @abstractmethod
    async def load_for_verkey(self, their_verkey: str) -> Optional[Pairwise]:
        raise NotImplemented

    async def enumerate(self):
        cur = 0
        await self._start_loading()
        try:
            while True:
                success, collection = await self._partial_load()
                if success:
                    for p in collection:
                        yield cur, p
                        cur += 1
                else:
                    break
        finally:
            await self._stop_loading()

    @abstractmethod
    async def _start_loading(self):
        raise NotImplemented

    @abstractmethod
    async def _partial_load(self) -> (bool, List[Pairwise]):
        raise NotImplemented

    @abstractmethod
    async def _stop_loading(self):
        raise NotImplemented

    def __aiter__(self):
        return self


class WalletPairwiseList(AbstractPairwiseList):

    def __init__(self, api: (AbstractPairwise, AbstractDID)):
        self._api_pairwise = api[0]
        self._api_did = api[1]
        self.__is_loading = False

    async def create(self, pairwise: Pairwise):
        await self._api_did.store_their_did(did=pairwise.their.did, verkey=pairwise.their.verkey)
        metadata = pairwise.metadata or {}
        metadata.update(self._build_metadata(pairwise))
        await self._api_pairwise.create_pairwise(
            their_did=pairwise.their.did,
            my_did=pairwise.me.did,
            metadata=metadata,
            tags=self._build_tags(pairwise)
        )

    async def update(self, pairwise: Pairwise):
        metadata = pairwise.metadata or {}
        metadata.update(self._build_metadata(pairwise))
        await self._api_pairwise.set_pairwise_metadata(
            their_did=pairwise.their.did,
            metadata=metadata,
            tags=self._build_tags(pairwise)
        )

    async def is_exists(self, their_did: str) -> bool:
        return await self._api_pairwise.is_pairwise_exists(their_did=their_did)

    async def ensure_exists(self, pairwise: Pairwise):
        if await self.is_exists(their_did=pairwise.their.did):
            await self.update(pairwise)
        else:
            await self.create(pairwise)

    async def load_for_did(self, their_did: str) -> Optional[Pairwise]:
        if await self.is_exists(their_did):
            raw = await self._api_pairwise.get_pairwise(their_did)
            metadata = raw['metadata']
            pairwise = self._restore_pairwise(metadata)
            return pairwise
        else:
            return None

    async def load_for_verkey(self, their_verkey: str) -> Optional[Pairwise]:
        collection, count = await self._api_pairwise.search(tags={'their_verkey': their_verkey}, limit=1)
        if collection:
            metadata = collection[0]['metadata']
            pairwise = self._restore_pairwise(metadata)
            return pairwise
        else:
            return None

    async def _start_loading(self):
        self.__is_loading = True

    async def _partial_load(self) -> (bool, List[Pairwise]):
        if self.__is_loading:
            items = await self._api_pairwise.list_pairwise()
            self.__is_loading = False
            return True, [self._restore_pairwise(item['metadata']) for item in items]
        else:
            return False, []

    async def _stop_loading(self):
        self.__is_loading = False

    @staticmethod
    def _build_tags(p: Pairwise):
        return {
            'my_did': p.me.did,
            'my_verkey': p.me.verkey,
            'their_verkey': p.their.verkey
        }

    @staticmethod
    def _restore_pairwise(metadata: dict):
        pairwise = Pairwise(
            me=Pairwise.Me(
                did=metadata.get('me', {}).get('did', None),
                verkey=metadata.get('me', {}).get('verkey', None),
                did_doc=metadata.get('me', {}).get('did_doc', None)
            ),
            their=Pairwise.Their(
                did=metadata.get('their', {}).get('did', None),
                verkey=metadata.get('their', {}).get('verkey', None),
                label=metadata.get('their', {}).get('label', None),
                endpoint=metadata.get('their', {}).get('endpoint', {}).get('address', None),
                routing_keys=metadata.get('their', {}).get('endpoint', {}).get('routing_keys', None),
                did_doc=metadata.get('their', {}).get('did_doc', None)
            ),
            metadata=metadata
        )
        return pairwise

    @staticmethod
    def _build_metadata(pairwise: Pairwise) -> dict:
        metadata = {
            'me': {
                'did': pairwise.me.did,
                'verkey': pairwise.me.verkey,
                'did_doc': pairwise.me.did_doc
            },
            'their': {
                'did': pairwise.their.did,
                'verkey': pairwise.their.verkey,
                'label': pairwise.their.label,
                'endpoint': {
                    'address': pairwise.their.endpoint,
                    'routing_keys': pairwise.their.routing_keys
                },
                'did_doc': pairwise.their.did_doc
            }
        }
        return metadata
