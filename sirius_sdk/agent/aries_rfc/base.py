from abc import ABC, abstractmethod

from ..coprotocols import *


ARIES_DOC_URI = 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/'
THREAD_DECORATOR = '~thread'


class AriesProtocolMessage(Message):

    PROTOCOL = None
    NAME = None

    def __init__(self, id_: str=None, version: str='1.0', *args, **kwargs):
        if self.NAME and ('@type' not in dict(*args, **kwargs)):
            kwargs['@type'] = Type(
                doc_uri=ARIES_DOC_URI, protocol=self.PROTOCOL, name=self.NAME, version=version
            ).normalized
        super().__init__(*args, **kwargs)
        if id_ is not None:
            self['@id'] = id_
        if self.doc_uri != ARIES_DOC_URI:
            raise SiriusValidationError('Unexpected doc_uri "%s"' % self.doc_uri)
        if self.protocol != self.PROTOCOL:
            raise SiriusValidationError('Unexpected protocol "%s"' % self.protocol)
        if self.name != self.NAME:
            raise SiriusValidationError('Unexpected name "%s"' % self.name)

    def validate(self):
        validate_common_blocks(self)


class RegisterMessage(type):

    def __new__(meta, name, bases, class_dict):
        cls = type.__new__(meta, name, bases, class_dict)
        if issubclass(cls, AriesProtocolMessage):
            register_message_class(cls, protocol=cls.PROTOCOL, name=cls.NAME)
        return cls


class AbstractStateMachine(ABC):

    def __init__(self, transport: AbstractCoProtocolTransport, time_to_live: int=60):
        self.__transport = transport
        self.__time_to_live = time_to_live

    @property
    def time_to_live(self) -> int:
        return self.__time_to_live

    async def begin(self):
        await self.__transport.start(self.protocols, self.__time_to_live)

    async def end(self):
        await self.__transport.stop()

    @property
    @abstractmethod
    def protocols(self) -> List[str]:
        raise NotImplemented('Need to be implemented in descendant')
