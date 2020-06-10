from functools import lru_cache
from typing import Optional, Union
import base64

import base58
import nacl.bindings
import nacl.exceptions
import nacl.utils

from ..exceptions import SiriusCryptoError


def b64_to_bytes(val: Union[str, bytes], urlsafe=False) -> bytes:
    """Convert a base 64 string to bytes."""
    if isinstance(val, str):
        val = val.encode('ascii')
    if urlsafe:
        missing_padding = len(val) % 4
        if missing_padding:
            val += b'=' * (4 - missing_padding)
        return base64.urlsafe_b64decode(val)
    return base64.b64decode(val)


def bytes_to_b64(val: bytes, urlsafe=False) -> str:
    """Convert a byte string to base 64."""
    if urlsafe:
        return base64.urlsafe_b64encode(val).decode("ascii")
    return base64.b64encode(val).decode("ascii")


@lru_cache(maxsize=16)
def b58_to_bytes(val: str) -> bytes:
    """
    Convert a base 58 string to bytes.

    Small cache provided for key conversions which happen frequently in pack
    and unpack and message handling.
    """
    return base58.b58decode(val)


@lru_cache(maxsize=16)
def bytes_to_b58(val: bytes) -> str:
    """
    Convert a byte string to base 58.

    Small cache provided for key conversions which happen frequently in pack
    and unpack and message handling.
    """
    return base58.b58encode(val).decode("ascii")


def create_keypair(seed: bytes = None) -> (bytes, bytes):
    """
    Create a public and private signing keypair from a seed value.

    Args:
        seed: Seed for keypair

    Returns:
        A tuple of (public key, secret key)

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

    Returns:
        A new random seed

    """
    return nacl.utils.random(nacl.bindings.crypto_secretbox_KEYBYTES)


def validate_seed(seed: Union[str, bytes]) -> Optional[bytes]:
    """
    Convert a seed parameter to standard format and check length.

    Args:
        seed: The seed to validate

    Returns:
        The validated and encoded seed

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
