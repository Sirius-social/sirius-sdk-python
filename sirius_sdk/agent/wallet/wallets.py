from ..connections import AgentRPC
from .impl.did import DIDProxy
from .impl.cache import CacheProxy
from .impl.crypto import CryptoProxy
from .impl.ledger import LedgerProxy
from .impl.pairwise import PairwiseProxy
from .impl.anoncreds import AnonCredsProxy
from .impl.non_secrets import NonSecretsProxy


class DynamicWallet:

    def __init(self, rpc: AgentRPC):
        self.__rpc = rpc
        self.__did = DIDProxy(rpc)
        self.__crypto = CryptoProxy(rpc)
        self.__cache = CacheProxy(rpc)
        self.__pairwise = PairwiseProxy(rpc)
        self.__non_secrets = NonSecretsProxy(rpc)
        self.__ledger = LedgerProxy(rpc)
        self.__anoncreds = AnonCredsProxy(rpc)

    @property
    def did(self) -> DIDProxy:
        return self.__did

    @property
    def crypto(self) -> CryptoProxy:
        return self.__crypto

    @property
    def cache(self) -> CacheProxy:
        return self.__cache

    @property
    def ledger(self) -> LedgerProxy:
        return self.__ledger

    @property
    def pairwise(self) -> PairwiseProxy:
        return self.__pairwise

    @property
    def anoncreds(self) -> AnonCredsProxy:
        return self.__anoncreds

    @property
    def non_secrets(self) -> NonSecretsProxy:
        return self.__non_secrets

    async def generate_wallet_key(self, seed: str = None) -> str:
        return await self.__rpc.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/generate_wallet_key',
            params=dict(seed=seed)
        )
