import time
import json
import struct
import base64
import logging
from typing import Any
from datetime import datetime, timedelta
from typing import Optional

from pytime import pytime

from sirius_sdk.agent.wallet.abstract.crypto import AbstractCrypto


def utc_to_str(dt: datetime):
    return dt.strftime('%Y-%m-%dT%H:%M:%S') + '+0000'


def str_to_utc(s: str, raise_exceptions: bool = True) -> Optional[datetime]:
    tz_shift = None
    try:
        if '+' in s:
            s, shift = s.split('+')
            tz_shift = timedelta(hours=int(shift))
        s = s.replace('T', ' ')
        ret = pytime.parse(s)
        return ret + tz_shift
    except:
        logging.exception('Error while parse datetime')
        if raise_exceptions:
            raise
        else:
            return None


async def sign(crypto: AbstractCrypto, value: Any, verkey: str, exclude_sig_data: bool = False) -> dict:
    timestamp_bytes = struct.pack(">Q", int(time.time()))

    sig_data_bytes = timestamp_bytes + json.dumps(value).encode('ascii')
    sig_data = base64.urlsafe_b64encode(sig_data_bytes).decode('ascii')

    signature_bytes = await crypto.crypto_sign(verkey, sig_data_bytes)
    signature = base64.urlsafe_b64encode(
        signature_bytes
    ).decode('ascii')

    data = {
        "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/signature/1.0/ed25519Sha512_single",
        "signer": verkey,
        "signature": signature
    }
    if not exclude_sig_data:
        data['sig_data'] = sig_data

    return data


async def verify_signed(crypto: AbstractCrypto, signed: dict) -> (Any, bool):
    signature_bytes = base64.urlsafe_b64decode(signed['signature'].encode('ascii'))
    sig_data_bytes = base64.urlsafe_b64decode(signed['sig_data'].encode('ascii'))
    sig_verified = await crypto.crypto_verify(
        signed['signer'],
        sig_data_bytes,
        signature_bytes
    )
    data_bytes = base64.urlsafe_b64decode(signed['sig_data'])
    timestamp = struct.unpack(">Q", data_bytes[:8])
    field_json = data_bytes[8:]
    if isinstance(field_json, bytes):
        field_json = field_json.decode('utf-8')
    return json.loads(field_json), sig_verified
