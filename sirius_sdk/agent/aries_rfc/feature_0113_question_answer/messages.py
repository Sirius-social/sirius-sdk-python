import hashlib
import datetime
from typing import Optional, List

from sirius_sdk.agent.wallet.abstract.crypto import AbstractCrypto
from sirius_sdk.agent.aries_rfc.utils import sign
from sirius_sdk.agent.aries_rfc.mixins import ThreadMixin
from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage


class Question(ThreadMixin, AriesProtocolMessage, metaclass=RegisterMessage):
    """Implementation of Question

    https://github.com/hyperledger/aries-rfcs/tree/master/features/0113-question-answer
    """

    PROTOCOL = 'questionanswer'
    NAME = 'question'

    def __init__(
            self, valid_responses: List[str] = None, question_text: Optional[str] = None,
            question_detail: Optional[str] = None, nonce: Optional[str] = None,
            signature_required: Optional[bool] = None, locale: Optional[str] = None,
            expires_time: Optional[str] = None,
            *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if locale is not None:
            self['~l10n'] = {"locale": locale}
        if valid_responses is not None:
            self['valid_responses'] = [{'text': s} for s in valid_responses]
        if question_text is not None:
            self['question_text'] = question_text
        if question_detail is not None:
            self['question_detail'] = question_detail
        if nonce is not None:
            self['nonce'] = nonce
        if signature_required is not None:
            self['signature_required'] = signature_required
        if expires_time:
            timing = self.get('~timing', {})
            timing['expires_time'] = expires_time
            self['~timing'] = timing

    @property
    def locale(self) -> Optional[str]:
        return self.get('~l10n', {}).get('locale', None)

    @property
    def valid_responses(self) -> List[str]:
        return list(self.get('valid_responses', {}).values())

    @property
    def question_text(self) -> Optional[str]:
        return self.get('question_text', None)

    @property
    def question_detail(self) -> Optional[str]:
        return self.get('question_detail', None)

    @property
    def nonce(self) -> Optional[str]:
        return self.get('nonce', None)

    @property
    def signature_required(self) -> Optional[bool]:
        return self.get('signature_required', None)

    @property
    def expires_time(self) -> Optional[str]:
        return self.get('~timing', {}).get('expires_time', None)

    def set_ttl(self, seconds: int):
        expire_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
        timing = self.get('~timing', {})
        timing['expires_time'] = expire_at.replace(tzinfo=datetime.timezone.utc, microsecond=0).isoformat()
        self['~timing'] = timing


class Answer(ThreadMixin, AriesProtocolMessage, metaclass=RegisterMessage):
    """Implementation of Answer

    https://github.com/hyperledger/aries-rfcs/tree/master/features/0113-question-answer
    """

    PROTOCOL = 'questionanswer'
    NAME = 'answer'

    def __init__(
            self, response: Optional[str] = None, thread_id: Optional[str] = None,
            out_time: Optional[str] = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if response is not None:
            self['response'] = response
        if thread_id is not None:
            self.thread_id = thread_id
        if out_time is not None:
            timing = self.get('~timing', {})
            timing['out_time'] = out_time
            self['~timing'] = timing

    @property
    def response(self) -> Optional[str]:
        return self.get('response', None)

    @property
    def out_time(self) -> Optional[str]:
        return self.get('~timing', {}).get('out_time', None)

    def set_out_time(self):
        timing = self.get('~timing', {})
        timing['out_time'] = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
        self['~timing'] = timing

    async def sign(self, crypto: AbstractCrypto, q: Question, verkey: str):
        data = q.question_text or '' + self.response or '' + q.nonce or ''
        hashfunc = hashlib.sha256
        hasher = hashfunc()
        hasher.update(data.encode('utf-8'))
        digest = hasher.digest()
        self['response~sig'] = await sign(crypto, digest, verkey)
