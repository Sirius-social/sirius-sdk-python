from sirius_sdk.agent.coprotocols import *


VALID_DOC_URI = ['https://didcomm.org/', 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/']
ARIES_DOC_URI = VALID_DOC_URI[1]
THREAD_DECORATOR = '~thread'


class AriesProtocolMessage(Message):

    DOC_URI = ARIES_DOC_URI
    PROTOCOL = None
    NAME = None

    def __init__(self, id_: str = None, version: str = '1.0', doc_uri: str = None, *args, **kwargs):
        if self.NAME and ('@type' not in dict(*args, **kwargs)):
            kwargs['@type'] = str(
                Type(
                    doc_uri=doc_uri or self.DOC_URI,
                    protocol=self.PROTOCOL,
                    name=self.NAME, version=version
                )
            )
        super().__init__(*args, **kwargs)
        if id_ is not None:
            self['@id'] = id_
        if self.doc_uri not in VALID_DOC_URI:
            raise SiriusValidationError('Unexpected doc_uri "%s"' % self.doc_uri)
        if self.protocol != self.PROTOCOL:
            raise SiriusValidationError('Unexpected protocol "%s"' % self.protocol)
        if self.name != self.NAME:
            raise SiriusValidationError('Unexpected name "%s"' % self.name)

    def validate(self):
        validate_common_blocks(self)


class AriesProblemReport(AriesProtocolMessage):

    NAME = 'problem_report'

    def __init__(self, problem_code: str=None, explain: str=None, thread_id: str=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if problem_code:
            self['problem-code'] = problem_code
        if explain:
            self['explain'] = explain
        if thread_id is not None:
            thread = self.get(THREAD_DECORATOR, {})
            thread['thid'] = thread_id
            self[THREAD_DECORATOR] = thread

    @property
    def problem_code(self) -> str:
        return self.get('problem-code', '')

    @property
    def explain(self) -> str:
        return self.get('explain', '')


class RegisterMessage(type):

    def __new__(meta, name, bases, class_dict):
        cls = type.__new__(meta, name, bases, class_dict)
        if issubclass(cls, AriesProtocolMessage):
            register_message_class(cls, protocol=cls.PROTOCOL, name=cls.NAME)
        return cls


