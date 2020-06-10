from functools import lru_cache
from typing import Optional, Union
import base64

import base58
import nacl.bindings
import nacl.exceptions
import nacl.utils

from ..errors.exceptions import SiriusCryptoError


def b64_to_bytes(value: Union[str, bytes], urlsafe: bool=False) -> bytes:
    """Convert a base 64 string to bytes.

    :param value: (str, bytes) input base64 value
    :param urlsafe: (bool) flag if needed to convert to urlsafe presentation
    :return: bytes array
    """
    if isinstance(value, str):
        value = value.encode('ascii')
    if urlsafe:
        missing_padding = len(value) % 4
        if missing_padding:
            value += b'=' * (4 - missing_padding)
        return base64.urlsafe_b64decode(value)
    return base64.b64decode(value)


def bytes_to_b64(value: bytes, urlsafe=False) -> str:
    """Convert a byte string to base 64.

    :param value: (bytes) input bytes array
    :param urlsafe: (bool) flag if needed to convert to urlsafe presentation
    :return base64 presentation
    """
    if urlsafe:
        return base64.urlsafe_b64encode(value).decode("ascii")
    else:
        return base64.b64encode(value).decode("ascii")


@lru_cache(maxsize=16)
def b58_to_bytes(value: str) -> bytes:
    """
    Convert a base 58 string to bytes.

    Small cache provided for key conversions which happen frequently in pack
    and unpack and message handling.
    """
    return base58.b58decode(value)


@lru_cache(maxsize=16)
def bytes_to_b58(value: bytes) -> str:
    """
    Convert a byte string to base 58.

    Small cache provided for key conversions which happen frequently in pack
    and unpack and message handling.
    """
    return base58.b58encode(value).decode("ascii")


def create_keypair(seed: bytes = None) -> (bytes, bytes):
    """
    Create a public and private signing keypair from a seed value.

    :param seed: (bytes) Seed for keypair
    :return A tuple of (public key, secret key)
    """
    if seed:
        validate_seed(seed)
    else:
        seed = random_seed()
    pk, sk = nacl.bindings.crypto_sign_seed_keypair(seed)
    return pk, sk


def random_seed() -> bytes:
    """
    Generate a random seed value.

    :return A new random seed
    """
    return nacl.utils.random(nacl.bindings.crypto_secretbox_KEYBYTES)


def validate_seed(seed: Union[str, bytes]) -> Optional[bytes]:
    """
    Convert a seed parameter to standard format and check length.

    :param seed: (str, bytes) The seed to validate
    :return The validated and encoded seed
    """
    if not seed:
        return None
    if isinstance(seed, str):
        if "=" in seed:
            seed = b64_to_bytes(seed)
        else:
            seed = seed.encode("ascii")
    if not isinstance(seed, bytes):
        raise SiriusCryptoError("Seed value is not a string or bytes")
    if len(seed) != 32:
        raise SiriusCryptoError("Seed value must be 32 bytes in length")
    return seed
