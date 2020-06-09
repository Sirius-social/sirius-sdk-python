from enum import Enum

from .did import *
from .cache import *
from .crypto import *
from .ledger import *
from .pairwise import *
from .anoncreds import *
from .non_secrets import *


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


__all__ = ["did", "cache", "crypto", "ledger", "pairwise", "anoncreds", "non_secrets", "KeyDerivationMethod"]
