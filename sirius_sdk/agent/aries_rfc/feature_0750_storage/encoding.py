import json
from enum import Enum
from dataclasses import dataclass
from typing import Union, List, Optional

from sirius_sdk.encryption import b64_to_bytes

from .errors import EncryptionError


class ConfidentialStorageEncType(Enum):
    # This enc-type typically used to save chunked structure of stream
    # that was encoded outside (on upper levels)
    UNKNOWN = 'UNKNOWN'
    # X25519
    X25519KeyAgreementKey2019 = 'X25519KeyAgreementKey2019'


@dataclass
class KeyPair:
    # Public Key
    pk: str

    # SecretKey
    sk: str
    

@dataclass
class EncHeader:
    kid: str
    sender: str = None
    iv: str = None


@dataclass
class EncRecipient:
    encrypted_key: str
    header: EncHeader


@dataclass
class JWE:
    enc: str = 'xchacha20poly1305_ietf'
    typ: str = 'JWE/1.0'
    alg: str = 'Anoncrypt'
    iv: str = None
    recipients: List[EncRecipient] = None

    def __post_init__(self):
        if self.recipients is None:
            self.recipients = []

    def as_json(self) -> dict:
        return {
            'enc': self.enc,
            'typ': self.typ,
            'alg': self.alg,
            'iv': self.iv,
            'recipients': [
                {
                    'encrypted_key': recip.encrypted_key,
                    'header': {
                        'kid': recip.header.kid,
                        'sender': recip.header.sender,
                        'iv': recip.header.iv
                    }
                }
                for recip in self.recipients
            ]
        }

    def from_json(self, js: dict):
        try:
            self.enc = js['enc']
            self.typ = js['typ']
            self.alg = js['alg']
            self.iv = js.get('iv', None)
            self.recipients = [
                EncRecipient(
                    encrypted_key=recip['encrypted_key'],
                    header=EncHeader(
                        kid=recip['header']['kid'],
                        sender=recip['header'].get('sender', None),
                        iv=recip['header'].get('iv', None)
                    )
                )
                for recip in js['recipients']
            ]
        except (LookupError, ValueError) as e:
            msg = str(e)
            raise EncryptionError(msg)


def parse_protected(jwe: Union[str, bytes, dict]) -> dict:
    if isinstance(jwe, str):
        d = json.loads(jwe)
    elif isinstance(jwe, bytes):
        d = json.loads(jwe.decode())
    else:
        d = jwe
    jwe_json = json.loads(b64_to_bytes(d["protected"], urlsafe=True).decode("ascii"))
    return jwe_json
