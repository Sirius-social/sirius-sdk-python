import base64
from typing import Any

from sirius_sdk.agent.wallet import CacheOptions, PurgeOptions, RetrieveRecordOptions, NYMRole, PoolAction, KeyDerivationMethod
from sirius_sdk.rpc.futures import Future
from sirius_sdk.messaging import Message, Type
from sirius_sdk.errors.exceptions import SiriusInvalidType, SiriusInvalidPayloadStructure


MSG_TYPE_FUTURE = 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/sirius_rpc/1.0/future'


CLS_MAP = {
    'application/cache-options': CacheOptions,
    'application/purge-options': PurgeOptions,
    'application/retrieve-record-options': RetrieveRecordOptions,
    'application/nym-role': NYMRole,
    'application/pool-action': PoolAction,
    'application/key-derivation-method': KeyDerivationMethod,
}
CLS_MAP_REVERT = {v: k for k, v in CLS_MAP.items()}


def serialize_variable(var: Any) -> (str, Any):
    """Serialize input variable to JSON-compatible string

    :param var: input variable
    :return: tuple (type, variable serialized dump)
    """
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


def deserialize_variable(payload: Any, typ: str=None) -> Any:
    """Deserialize variable from string according to type

    :param payload: input variable
    :param typ: variable type
    :return: deserialized variable
    """
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


def build_request(msg_type: str, future: Future, params: dict) -> Message:
    """

    :param msg_type: Aries RFCs attribute
        https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0020-message-types
    :param future: Future to check response routine is completed
    :param params: RPC call params
    :return: RPC service packet
    """
    typ = Type.from_str(msg_type)
    if typ.protocol not in ['sirius_rpc', 'admin', 'microledgers']:
        raise SiriusInvalidType('Expect sirius_rpc protocol')
    return Message({
        '@type': msg_type,
        '@promise': future.promise,
        'params': {k: incapsulate_param(v) for k, v in params.items()}
    })


def build_response(packet: Message):
    if packet.get('@type') == MSG_TYPE_FUTURE:
        if packet.get('~thread', None) is not None:
            parsed = {
                'exception': None,
                'value': None
            }
            exception = packet['exception']
            if exception:
                parsed['exception'] = exception
            else:
                value = packet['value']
                if packet['is_tuple']:
                    parsed['value'] = tuple(value)
                elif packet['is_bytes']:
                    parsed['value'] = base64.b64decode(value.encode('ascii'))
                else:
                    parsed['value'] = value
            return parsed
        else:
            raise SiriusInvalidPayloadStructure('Expect ~thread decorator')
    else:
        raise SiriusInvalidType('Expect message type "%s"' % MSG_TYPE_FUTURE)
