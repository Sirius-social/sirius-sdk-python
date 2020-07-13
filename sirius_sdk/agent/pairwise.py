from abc import ABC, abstractmethod
from typing import List, Optional

from .wallet.abstract.pairwise import AbstractPairwise


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

    def __init__(self, api: AbstractPairwise):
        self._api = api

    async def create(self, pairwise: Pairwise):
        await self._api.create_pairwise(
            their_did=pairwise.their.did,
            my_did=pairwise.me.did,
            metadata=pairwise.metadata,
            tags=self._build_tags(pairwise)
        )

    async def update(self, pairwise: Pairwise):
        await self._api.set_pairwise_metadata(
            their_did=pairwise.their.did,
            metadata=pairwise.metadata,
            tags=self._build_tags(pairwise)
        )

    async def is_exists(self, their_did: str) -> bool:
        return await self._api.is_pairwise_exists(their_did=their_did)

    async def ensure_exists(self, pairwise: Pairwise):
        if await self.is_exists(their_did=pairwise.their.did):
            await self.update(pairwise)
        else:
            await self.create(pairwise)

    async def load_for_did(self, their_did: str) -> Optional[Pairwise]:
        if await self.is_exists(their_did):
            raw = await self._api.get_pairwise(their_did)
            metadata = raw['metadata']
            pairwise = Pairwise(
                me=Pairwise.Me(
                    did=raw['me']['did'],
                    verkey=raw['me']['verkey']
                ),
                their=Pairwise.Their(
                    did=raw['their']['did'],
                    verkey=raw['their']['verkey'],
                    label=raw['their']['label'],
                    endpoint=raw['their']['endpoint']['address'],
                    routing_keys=raw['their']['endpoint']['routing_keys']
                ),
                metadata=metadata
            )
            return pairwise
        else:
            return None

    async def load_for_verkey(self, their_verkey: str) -> Optional[Pairwise]:
        pass

    @staticmethod
    def _build_tags(p: Pairwise):
        return {
            'my_did': p.me.did,
            'my_verkey': p.me.verkey,
            'their_verkey': p.their.verkey
        }
