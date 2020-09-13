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

        def __init__(self, did: str, label: str, endpoint: str, verkey: str, routing_keys: List[str]=None):
            self.did = did
            self.label = label
            super().__init__(endpoint, verkey, routing_keys)

    class Me:

        def __init__(self, did, verkey):
            self.did = did
            self.verkey = verkey

        def __eq__(self, other):
            if isinstance(other, Pairwise.Me):
                return self.did == other.did and self.verkey == other.verkey

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


class WalletPairwiseList(AbstractPairwiseList):

    def __init__(self, api: (AbstractPairwise, AbstractDID)):
        self._api_pairwise = api[0]
        self._api_did = api[1]

    async def create(self, pairwise: Pairwise):
        await self._api_did.store_their_did(did=pairwise.their.did, verkey=pairwise.their.verkey)
        await self._api_pairwise.create_pairwise(
            their_did=pairwise.their.did,
            my_did=pairwise.me.did,
            metadata=pairwise.metadata,
            tags=self._build_tags(pairwise)
        )

    async def update(self, pairwise: Pairwise):
        await self._api_pairwise.set_pairwise_metadata(
            their_did=pairwise.their.did,
            metadata=pairwise.metadata,
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
                verkey=metadata.get('me', {}).get('verkey', None)
            ),
            their=Pairwise.Their(
                did=metadata.get('their', {}).get('did', None),
                verkey=metadata.get('their', {}).get('verkey', None),
                label=metadata.get('their', {}).get('label', None),
                endpoint=metadata.get('their', {}).get('endpoint', {}).get('address', None),
                routing_keys=metadata.get('their', {}).get('endpoint', {}).get('routing_keys', None),
            ),
            metadata=metadata
        )
        return pairwise
