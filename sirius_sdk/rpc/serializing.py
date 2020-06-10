import base64
from typing import Any

from sirius_sdk.agent.wallet.abstract import CacheOptions, PurgeOptions
from sirius_sdk.agent.wallet.abstract import RetrieveRecordOptions
from sirius_sdk.agent.wallet.abstract import NYMRole, PoolAction
from sirius_sdk.agent.wallet.abstract import KeyDerivationMethod
from ..rpc.futures import Future


CLS_MAP = {
    'application/cache-options': CacheOptions,
    'application/purge-options': PurgeOptions,
    'application/retrieve-record-options': RetrieveRecordOptions,
    'application/nym-role': NYMRole,
    'application/pool-action': PoolAction,
    'application/key-derivation-method': KeyDerivationMethod,
}
CLS_MAP_REVERT = {v: k for k, v in CLS_MAP.items()}


def serialize_variable(var: Any):
    if isinstance(var, CacheOptions):
        return CLS_MAP_REVERT[CacheOptions], var.serialize()
    elif isinstance(var, PurgeOptions):
        return CLS_MAP_REVERT[PurgeOptions], var.serialize()
    elif isinstance(var, RetrieveRecordOptions):
        return CLS_MAP_REVERT[RetrieveRecordOptions], var.serialize()
    elif isinstance(var, NYMRole):
        return CLS_MAP_REVERT[NYMRole], var.serialize()
    elif isinstance(var, PoolAction):
        return CLS_MAP_REVERT[PoolAction], var.serialize()
    elif isinstance(var, KeyDerivationMethod):
        return CLS_MAP_REVERT[KeyDerivationMethod], var.serialize()
    elif isinstance(var, bytes):
        return 'application/base64', base64.b64encode(var).decode('ascii')
    else:
        return None, var


def deserialize_variable(payload: Any, typ: str=None):
    if typ is None:
        return payload
    elif typ == 'application/base64':
        return base64.b64decode(payload.encode('ascii'))
    elif typ in CLS_MAP.keys():
        cls = CLS_MAP[typ]
        if issubclass(cls, NYMRole):
            inst = NYMRole.deserialize(payload)
        elif issubclass(cls, PoolAction):
            inst = PoolAction.deserialize(payload)
        elif issubclass(cls, KeyDerivationMethod):
            inst = KeyDerivationMethod.deserialize(payload)
        else:
            inst = cls()
            inst.deserialize(payload)
        return inst
    else:
        raise RuntimeError('Unexpected typ: "%s"' % typ)


def incapsulate_param(param):
    typ, payload = serialize_variable(param)
    return {
        'mime_type': typ,
        'payload': payload
    }


def deincapsulate_param(packet: dict):
    return deserialize_variable(packet['payload'], packet['mime_type'])


def build_request(msg_type: str, future: Future, params: dict) -> dict:
    return {
        '@type': msg_type,
        '@promise': future.promise,
        'params': {k: incapsulate_param(v) for k, v in params.items()}
    }
