import json
import base64
from typing import List, Optional
from collections import UserDict

from sirius_sdk.errors.exceptions import *
from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage, AriesProblemReport, THREAD_DECORATOR


CREDENTIAL_PREVIEW_TYPE = "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/issue-credential/1.0/credential-preview"
CREDENTIAL_TRANSLATION_TYPE = "https://github.com/Sirius-social/agent/tree/master/messages/credential-translation"
ISSUER_SCHEMA_TYPE = "https://github.com/Sirius-social/agent/tree/master/messages/issuer-schema"
CREDENTIAL_TRANSLATION_ID = "credential-translation"
ISSUER_SCHEMA_ID = "issuer-schema"


class ProposedAttrib(UserDict):

    def __init__(self, name: str, value: str, mime_type: str = None, **kwargs):
        super().__init__()
        self.data['name'] = name
        if mime_type:
            self.data['mime-type'] = mime_type
        self.data['value'] = value

    def to_json(self):
        return self.data


class AttribTranslation(UserDict):

    def __init__(self, attrib_name: str, translation: str, **kwargs):
        super().__init__()
        self.data['attrib_name'] = attrib_name
        self.data['translation'] = translation

    def to_json(self):
        return self.data


class BaseIssueCredentialMessage(AriesProtocolMessage, metaclass=RegisterMessage):

    PROTOCOL = 'issue-credential'
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


class IssueProblemReport(AriesProblemReport, metaclass=RegisterMessage):

    PROTOCOL = BaseIssueCredentialMessage.PROTOCOL


class ProposeCredentialMessage(BaseIssueCredentialMessage):

    NAME = 'propose-credential'

    def __init__(
            self, comment: str = None, proposal_attrib: List[ProposedAttrib] = None, schema_id: str = None,
            schema_name: str = None, schema_version: str = None, schema_issuer_did: str = None, cred_def_id: str = None,
            issuer_did: str = None, proposal_attrib_translation: List[AttribTranslation] = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if comment:
            self['comment'] = comment
        if schema_id:
            self['schema_id'] = schema_id
        if schema_name:
            self['schema_name'] = schema_name
        if schema_version:
            self['schema_version'] = schema_version
        if schema_issuer_did:
            self['schema_issuer_did'] = schema_issuer_did
        if cred_def_id:
            self['cred_def_id'] = cred_def_id
        if issuer_did:
            self['issuer_did'] = issuer_did
        if proposal_attrib:
            self['credential_proposal'] = {
                "@type": CREDENTIAL_PREVIEW_TYPE,
                "attributes": [attrib.to_json() for attrib in proposal_attrib]
            }
            if proposal_attrib_translation:
                self['~attach'] = [
                    {
                        "@type": CREDENTIAL_TRANSLATION_TYPE,
                        "id": CREDENTIAL_TRANSLATION_ID,
                        '~l10n': {"locale": self.locale},
                        "mime-type": "application/json",
                        "data": {
                            "json": [trans.to_json() for trans in proposal_attrib_translation]
                        }
                    }
                ]


class OfferCredentialMessage(BaseIssueCredentialMessage):

    NAME = 'offer-credential'

    def __init__(
            self, comment: str = None, offer: dict = None, cred_def: dict = None,
            preview: List[ProposedAttrib] = None, issuer_schema: dict = None, translation: List[AttribTranslation] = None,
            expires_time: str = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if comment:
            self['comment'] = comment
        if preview:
            preview = [ProposedAttrib(**item) for item in preview] if preview else None
            self["credential_preview"] = {
                "@type": CREDENTIAL_PREVIEW_TYPE,
                "attributes": [attrib.to_json() for attrib in preview]
            }
        if translation:
            translation = [AttribTranslation(**item) for item in translation]
        if offer and cred_def:
            payload = dict(**offer, **cred_def)
            self["offers~attach"] = [
                {
                    "@id": 'libindy-cred-offer-' + self.id,
                    "mime-type": "application/json",
                    "data": {
                        "base64": base64.b64encode(json.dumps(payload).encode()).decode()
                    }
                }
            ]
        if translation or issuer_schema:
            self['~attach'] = []
            if translation:
                self['~attach'].append(
                    {
                        "@type": CREDENTIAL_TRANSLATION_TYPE,
                        "id": CREDENTIAL_TRANSLATION_ID,
                        '~l10n': {"locale": self.locale},
                        "mime-type": "application/json",
                        "data": {
                            "json": [trans.to_json() for trans in translation]
                        }
                    }
                )
            if issuer_schema:
                self['~attach'].append(
                    {
                        "@type": ISSUER_SCHEMA_TYPE,
                        "id": ISSUER_SCHEMA_ID,
                        "mime-type": "application/json",
                        "data": {
                            "json": issuer_schema
                        }
                    }
                )
        if expires_time:
            self['~timing'] = {
                "expires_time": expires_time
            }

    @property
    def comment(self) -> Optional[str]:
        return self.get('comment', None)

    @property
    def preview(self) -> Optional[List[ProposedAttrib]]:
        preview = self.get('credential_preview', None)
        if (type(preview) is dict) and (preview.get('@type', None) == CREDENTIAL_PREVIEW_TYPE):
            attribs = preview.get('attributes', [])
            return [ProposedAttrib(**item) for item in attribs]
        else:
            return None

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
    def issuer_schema(self) -> Optional[dict]:
        attaches = self.get('~attach', [])
        cs = None
        for item in attaches:
            if item.get('@type', None) == ISSUER_SCHEMA_TYPE:
                cs = item
                break
        if cs:
            return cs.get('data', {}).get('json', [])
        else:
            return None

    @property
    def offer(self) -> Optional[dict]:
        try:
            _, offer, _ = self.parse()
        except SiriusValidationError:
            return None
        else:
            return offer

    @property
    def cred_def(self) -> Optional[dict]:
        try:
            _, _, cred_def = self.parse()
        except SiriusValidationError:
            return None
        else:
            return cred_def

    @property
    def expires_time(self) -> Optional[str]:
        return self.get('~timing', {}).get('expires_time', None)

    def parse(self) -> (dict, dict, dict):
        offer_attaches = self.get('offers~attach', None)
        if isinstance(offer_attaches, dict):
            offer_attaches = [offer_attaches]
        if (not type(offer_attaches) is list) or (type(offer_attaches) is list and len(offer_attaches) == 0):
            raise SiriusValidationError('Expected attribute "offer~attach" must contains cred-Offer and cred-Def')
        offer = offer_attaches[0]
        offer_body = None
        cred_def_body = None

        for attach in offer_attaches:
            raw_base64 = attach.get('data', {}).get('base64', None)
            if raw_base64:
                payload = json.loads(base64.b64decode(raw_base64).decode())
                offer_fields = ['key_correctness_proof', 'nonce', 'schema_id', 'cred_def_id']
                cred_def_fields = ['value', 'type', 'ver', 'schemaId', 'id', 'tag']
                if all([field in payload.keys() for field in offer_fields]):  # check if cred offer content
                    offer_body = {attr: val for attr, val in payload.items() if attr in offer_fields}
                if all([field in payload.keys() for field in cred_def_fields]):  # check if cred def content
                    cred_def_body = {attr: val for attr, val in payload.items() if attr in cred_def_fields}

        if not offer_body:
            raise SiriusValidationError('Expected offer~attach must contains Payload with offer')

        if not cred_def_body:
            raise SiriusValidationError('Expected offer~attach must contains Payload with cred_def data')

        return offer, offer_body, cred_def_body

    def validate(self):
        super().validate()
        if 'offers~attach' not in self:
            raise SiriusValidationError('Expected offer attribute "offers~attach" missing')
        self.parse()


class RequestCredentialMessage(BaseIssueCredentialMessage):

    NAME = 'request-credential'

    def __init__(
            self, comment: str = None, cred_request: dict = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if comment:
            self['comment'] = comment
        if cred_request:
            self["requests~attach"] = [
                {
                    "@id": 'cred-request-' + self.id,
                    "mime-type": "application/json",
                    "data": {
                        "base64": base64.b64encode(json.dumps(cred_request).encode()).decode()
                    }
                },
            ]

    @property
    def cred_request(self) -> Optional[dict]:
        request = self.get('requests~attach', None)
        if request:
            if isinstance(request, list):
                request = request[0]
            body = request.get('data').get('base64')
            body = base64.b64decode(body)
            body = json.loads(body.decode())
            return body
        else:
            return None

    def validate(self):
        super().validate()
        if 'requests~attach' not in self:
            raise SiriusValidationError('Expected offer attribute "requests~attach" missing')


class IssueCredentialMessage(BaseIssueCredentialMessage):

    NAME = 'issue-credential'

    def __init__(
            self, comment: str = None, cred: dict = None, cred_id: str = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if comment:
            self['comment'] = comment
        if cred:
            if cred_id:
                message_id = cred_id
            else:
                message_id = 'libindy-cred-' + self.id
            self["credentials~attach"] = [
                {
                    "@id": message_id,
                    "mime-type": "application/json",
                    "data": {
                        "base64": base64.b64encode(json.dumps(cred).encode()).decode()
                    }
                }
            ]

    @property
    def cred_id(self) -> Optional[str]:
        attaches = self.get('credentials~attach', None)
        if attaches:
            if isinstance(attaches, dict):
                attaches = [attaches]
            if isinstance(attaches, list):
                attach = attaches[0]
                return attach.get('@id', None)
            else:
                return None
        else:
            return None

    @property
    def cred(self) -> Optional[dict]:
        attaches = self.get('credentials~attach', None)
        if attaches:
            if isinstance(attaches, dict):
                attaches = [attaches]
            if isinstance(attaches, list):
                attach = attaches[0]
                b64 = attach.get('data', {}).get('base64', None)
                if b64:
                    body = base64.b64decode(b64)
                    body = json.loads(body.decode())
                    return body
                else:
                    return None
            else:
                return None
        else:
            return None

    def validate(self):
        super().validate()
        if 'credentials~attach' not in self:
            raise SiriusValidationError('Expected issue attribute "credentials~attach" missing')
        if self.cred is None:
            raise SiriusValidationError('Credential is empty in "credentials~attach" field')
