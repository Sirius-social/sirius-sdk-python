from typing import Optional

from sirius_sdk.agent.aries_rfc.base import THREAD_DECORATOR


class PleaseAckMixin:

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


class ThreadMixin:

    @property
    def thread_id(self) -> Optional[str]:
        return self.get(THREAD_DECORATOR, {}).get('thid', None)

    @thread_id.setter
    def thread_id(self, thid: str):
        thread = self.get(THREAD_DECORATOR, {})
        thread['thid'] = thid
        self[THREAD_DECORATOR] = thread
