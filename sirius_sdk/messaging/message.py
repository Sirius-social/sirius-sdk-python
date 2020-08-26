""" Define Message base class.

https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0020-message-types
https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0008-message-id-and-threading
"""
import json
import uuid

from sirius_sdk.errors.exceptions import *
from sirius_sdk.messaging.type import Type, Semver


# Registry for restoring message instance from payload
MSG_REGISTRY = {}


def generate_id():
    """ Generate a message id. """
    return str(uuid.uuid4())


class Message(dict):
    """ Message base class.
        Inherits from dict meaning it behaves like a dictionary.
    """
    __slots__ = (
        'mtc',
        '_type'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if '@type' not in self:
            raise SiriusInvalidMessage('No @type in message')

        if '@id' not in self:
            self['@id'] = generate_id()
        elif not isinstance(self['@id'], str):
            raise SiriusInvalidMessage('Message @id is invalid; must be str')

        if isinstance(self['@type'], Type):
            self._type = self['@type']
            self['@type'] = str(self._type)
        else:
            self._type = Type.from_str(self.type)

    @property
    def type(self):
        """ Shortcut for msg['@type'] """
        return self['@type']

    @property
    def id(self):  # pylint: disable=invalid-name
        """ Shortcut for msg['@id'] """
        return self['@id']

    @property
    def doc_uri(self) -> str:
        """ Get type doc_uri """
        return self._type.doc_uri

    @property
    def protocol(self) -> str:
        """ Get type protocol """
        return self._type.protocol

    @property
    def version(self) -> str:
        """ Get type version """
        return self._type.version

    @property
    def version_info(self) -> Semver:
        """ Get type version info """
        return self._type.version_info

    @property
    def name(self) -> str:
        """ Get type name """
        return self._type.name

    @property
    def normalized_version(self) -> str:
        """ Get type normalized version """
        return str(self._type.version_info)

    # Serialization
    @classmethod
    def deserialize(cls, serialized: str):
        """ Deserialize a message from a json string. """
        try:
            return cls(json.loads(serialized))
        except json.decoder.JSONDecodeError as err:
            raise SiriusInvalidMessage('Could not deserialize message') from err

    def serialize(self):
        """ Serialize a message into a json string. """
        return json.dumps(self)

    def pretty_print(self):
        """ return a 'pretty print' representation of this message. """
        return json.dumps(self, indent=2)

    def __eq__(self, other):
        if not isinstance(other, Message):
            return False

        return super().__eq__(other)

    def __hash__(self):
        return hash(self.id)


def register_message_class(cls, protocol: str, name: str=None):
    if issubclass(cls, Message):
        descriptor = MSG_REGISTRY.get(protocol, {})
        if name:
            descriptor[name] = cls
        else:
            descriptor['*'] = cls
        MSG_REGISTRY[protocol] = descriptor
    else:
        raise SiriusInvalidMessageClass()


def restore_message_instance(payload: dict) -> (bool, Message):
    if '@type' in payload:
        typ = Type.from_str(payload['@type'])
        descriptor = MSG_REGISTRY.get(typ.protocol, None)
        if descriptor:
            if typ.name in descriptor:
                cls = descriptor[typ.name]
            elif '*' in descriptor:
                cls = descriptor['*']
            else:
                cls = None
        else:
            cls = None
        if cls is not None:
            return True, cls(**payload)
        else:
            return False, None
    else:
        return False, None
