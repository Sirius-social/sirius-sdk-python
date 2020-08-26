from enum import Enum

from sirius_sdk.agent.wallet.abstract.did import *
from sirius_sdk.agent.wallet.abstract.cache import *
from sirius_sdk.agent.wallet.abstract.crypto import *
from sirius_sdk.agent.wallet.abstract.ledger import *
from sirius_sdk.agent.wallet.abstract.pairwise import *
from sirius_sdk.agent.wallet.abstract.anoncreds import *
from sirius_sdk.agent.wallet.abstract.non_secrets import *


class KeyDerivationMethod(Enum):

    DEFAULT = 'ARGON2I_MOD'
    FAST = 'ARGON2I_INT'
    RAW = 'RAW'

    def serialize(self):
        return self.value

    @staticmethod
    def deserialize(buffer: str):
        value = buffer
        if value == 'ARGON2I_MOD':
            return KeyDerivationMethod.DEFAULT
        elif value == 'ARGON2I_INT':
            return KeyDerivationMethod.FAST
        elif value == 'RAW':
            return KeyDerivationMethod.RAW
        else:
            raise RuntimeError('Unexpected value "%s"' % buffer)


__all__ = ["KeyDerivationMethod"]
