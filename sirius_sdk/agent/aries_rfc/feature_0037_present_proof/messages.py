import json
import uuid
import base64
from typing import List, Optional
from collections import UserDict

from sirius_sdk.errors.exceptions import *
from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage, AriesProblemReport, THREAD_DECORATOR


CREDENTIAL_TRANSLATION_TYPE = "https://github.com/Sirius-social/agent/tree/master/messages/credential-translation"
CREDENTIAL_TRANSLATION_ID = "credential-translation"


class ProposedAttrib(UserDict):

    def __init__(
            self, name: str, value: str = None, mime_type: str = None, referent: str = None, cred_def_id: str = None
    ):
        super().__init__()
        self.data['name'] = name
        if mime_type:
            self.data['mime-type'] = mime_type
        if value:
            self.data['value'] = value
        if referent:
            self.data['referent'] = referent
        if cred_def_id:
            self.data['cred_def_id'] = cred_def_id

    def to_json(self):
        return self.data


class ProposedPredicate(UserDict):

    def __init__(self, name: str, predicate: str, threshold, cred_def_id: str = None):
        super().__init__()
        self.data['name'] = name
        self.data['predicate'] = predicate
        self.data['threshold'] = threshold
        if cred_def_id:
            self.data['cred_def_id'] = cred_def_id

    def to_json(self):
        return self.data


class AttribTranslation(UserDict):

    def __init__(self, attrib_name: str, translation: str, **kwargs):
        super().__init__()
        self.data['attrib_name'] = attrib_name
        self.data['translation'] = translation

    def to_json(self):
        return self.data


class BasePresentProofMessage(AriesProtocolMessage, metaclass=RegisterMessage):

    PROTOCOL = 'present-proof'
    DEF_LOCALE = 'en'

    def __init__(self, locale: str = DEF_LOCALE, *args, **kwargs):
        version = kwargs.pop('version', '1.1')
        super().__init__(version=version, *args, **kwargs)
        self['~l10n'] = {"locale": locale}

    @property
    def locale(self) -> str:
        return self.get('~l10n', {}).get('locale', self.DEF_LOCALE)

    @property
    def ack_message_id(self) -> str:
        return self.get('~please_ack', {}).get('message_id', None) or self.id

    @property
    def please_ack(self) -> bool:
        """https://github.com/hyperledger/aries-rfcs/tree/master/features/0317-please-ack"""
        return self.get('~please_ack', None) is not None

    @please_ack.setter
    def please_ack(self, flag: bool):
        if flag:
            self['~please_ack'] = {'message_id': self.id}
        elif '~please_ack' in self:
            del self['~please_ack']

    @property
    def thread_id(self) -> Optional[str]:
        return self.get(THREAD_DECORATOR, {}).get('thid', None)

    @thread_id.setter
    def thread_id(self, thid: str):
        thread = self.get(THREAD_DECORATOR, {})
        thread['thid'] = thid
        self[THREAD_DECORATOR] = thread


class PresentProofProblemReport(AriesProblemReport, metaclass=RegisterMessage):

    PROTOCOL = BasePresentProofMessage.PROTOCOL


class RequestPresentationMessage(BasePresentProofMessage):

    NAME = 'request-presentation'

    def __init__(
            self, proof_request: dict = None, comment: str = None,
            translation: List[AttribTranslation] = None, expires_time: str = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if comment:
            self['comment'] = comment
        id_suffix = uuid.uuid4().hex
        if proof_request:
            self["request_presentations~attach"] = [
                {
                    "@id": "libindy-request-presentation-" + id_suffix,
                    "mime-type": "application/json",
                    "data": {
                        "base64": base64.b64encode(json.dumps(proof_request).encode()).decode()
                    }
                }
            ]
        if translation:
            translation = [AttribTranslation(**item) for item in translation]
            self['~attach'] = [
                {
                    "@type": CREDENTIAL_TRANSLATION_TYPE,
                    "id": CREDENTIAL_TRANSLATION_ID,
                    '~l10n': {"locale": self.locale},
                    "mime-type": "application/json",
                    "data": {
                        "json": [trans.to_json() for trans in translation]
                    }
                }
            ]
        if expires_time:
            self['~timing'] = {
                "expires_time": expires_time
            }

    @property
    def proof_request(self) -> Optional[dict]:
        attaches = self.get('request_presentations~attach', None)
        if not attaches:
            return None
        if type(attaches) is dict:
            attaches = [attaches]
        accum = {}
        for attach in attaches:
            payload = json.loads(base64.b64decode(attach['data']['base64']).decode())
            accum.update(payload)
        return accum

    @property
    def comment(self) -> Optional[str]:
        return self.get('comment', None)

    @property
    def translation(self) -> Optional[List[AttribTranslation]]:
        attaches = self.get('~attach', [])
        tr = None
        for item in attaches:
            if item.get('@type', None) == CREDENTIAL_TRANSLATION_TYPE:
                tr = item
                break
        if tr:
            translation = tr.get('data', {}).get('json', [])
            return [AttribTranslation(**item) for item in translation]
        else:
            return None

    @property
    def expires_time(self) -> Optional[str]:
        return self.get('~timing', {}).get('expires_time', None)


class PresentationMessage(BasePresentProofMessage):

    NAME = 'presentation'

    def __init__(self, proof: dict = None, comment: str = None, presentation_id: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if comment:
            self['comment'] = comment
        if proof:
            if not presentation_id:
                presentation_id = uuid.uuid4().hex
            self["presentations~attach"] = [
                {
                    "@id": "libindy-presentation-" + presentation_id,
                    "mime-type": "application/json",
                    "data": {
                        "base64": base64.b64encode(json.dumps(proof).encode()).decode()
                    }
                }
            ]

    @property
    def proof(self) -> Optional[dict]:
        attaches = self.get('presentations~attach', None)
        if not attaches:
            return None
        if type(attaches) is dict:
            attaches = [attaches]
        accum = {}
        for attach in attaches:
            payload = json.loads(base64.b64decode(attach['data']['base64']).decode())
            accum.update(payload)
        return accum

    @property
    def comment(self) -> Optional[str]:
        return self.get('comment', None)
