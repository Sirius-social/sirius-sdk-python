from enum import Enum


class ConfidentialStorageEncType(Enum):
    # This enc-type typically used to save chunked structure of stream
    # that was encoded outside (on upper levels)
    UNKNOWN = 'UNKNOWN'
    # X25519
    X25519KeyAgreementKey2019 = 'X25519KeyAgreementKey2019'
