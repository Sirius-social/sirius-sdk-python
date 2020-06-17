from ..connections import AgentRPC
from .impl.did import DIDProxy
from .impl.cache import CacheProxy
from .impl.crypto import CryptoProxy
from .impl.ledger import LedgerProxy
from .impl.pairwise import PairwiseProxy
from .impl.non_secrets import NonSecretsProxy


class DynamicWallet:

    def __init(self, rpc: AgentRPC):
        self.__did = DIDProxy(rpc)
        self.__crypto = CryptoProxy(rpc)
        self.__cache = CacheProxy(rpc)
        self.__pairwise = PairwiseProxy(rpc)
        self.__non_secrets = NonSecretsProxy(rpc)
        self.__ledger = LedgerProxy(rpc)

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
    def non_secrets(self) -> NonSecretsProxy:
        return self.__non_secrets
