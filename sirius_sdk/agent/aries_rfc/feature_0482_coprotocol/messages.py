from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage, THREAD_DECORATOR, \
    VALID_DOC_URI, AriesProblemReport
from typing import List, Optional, Dict


class CoProtocolMessage(AriesProtocolMessage, metaclass=RegisterMessage):
    """Aries feature 0482 Messages implementation

    https://github.com/hyperledger/aries-rfcs/tree/main/features/0482-coprotocol-protocol
    """
    DOC_URI = VALID_DOC_URI[0]
    PROTOCOL = 'coprotocol'

    def __init__(self, thid: str = None, pthid: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if thid or pthid:
            # https://github.com/hyperledger/aries-rfcs/tree/main/concepts/0011-decorators#basic-conventions
            threads = self.get(THREAD_DECORATOR, {})
            if thid:
                threads['thid'] = thid
            if pthid:
                threads['pthid'] = pthid
            self[THREAD_DECORATOR] = threads
        #
        for fld, value in kwargs.items():
            if fld not in ['id_', 'version', 'doc_uri']:
                self[fld] = value

    @property
    def thid(self) -> Optional[str]:
        return self.get(THREAD_DECORATOR, {}).get('thid', None)

    @thid.setter
    def thid(self, value: str):
        threads = self.get(THREAD_DECORATOR, {})
        threads['thid'] = value
        self[THREAD_DECORATOR] = threads

    @property
    def pthid(self) -> Optional[str]:
        return self.get(THREAD_DECORATOR, {}).get('pthid', None)


class CoProtocolBind(CoProtocolMessage, metaclass=RegisterMessage):
    NAME = 'bind'

    def __init__(
            self, thid: str = None, pthid: str = None, co_binding_id: str = None,
            cast: List[Dict] = None, *args, **kwargs
    ):
        super().__init__(thid=thid, pthid=pthid, *args, **kwargs)
        self['co_binding_id'] = co_binding_id
        if cast:
            self['cast'] = cast


class CoProtocolAttach(CoProtocolMessage, metaclass=RegisterMessage):
    NAME = 'attach'


class CoProtocolInput(CoProtocolMessage, metaclass=RegisterMessage):
    NAME = 'input'


class CoProtocolOutput(CoProtocolMessage, metaclass=RegisterMessage):
    NAME = 'output'


class CoProtocolDetach(CoProtocolMessage, metaclass=RegisterMessage):
    NAME = 'detach'


class CoProtocolProblemReport(AriesProblemReport, metaclass=RegisterMessage):
    PROTOCOL = CoProtocolMessage.PROTOCOL
