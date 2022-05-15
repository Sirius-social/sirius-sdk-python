import io
from abc import ABC, abstractmethod
from typing import List, Optional
from contextlib import asynccontextmanager

from sirius_sdk.encryption import bytes_to_b58


class RawByteStorage:
    """Layer A: raw bytes storage (Cloud, DB, File-system, Mobile, etc)

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    pass


class EncryptedDataVault:
    """Layer B: Encrypted Vault Storage

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """

    class VaultConfig:
        pass

    class EncryptedDocument:
        pass

    class Indexes:
        pass


class AuthProvider:
    """Layer C: Authorization (policy enforcement point)

    see details: https://identity.foundation/confidential-storage/#ecosystem-overview
    """
    pass
