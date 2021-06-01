from typing import Optional, List
import base64

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


class Attach(dict):

    def __init__(self, id: str = None, mime_type: str = None, filename: str = None, lastmod_time: str = None,
                 description: str = None, data: bytes = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if id is not None:
            self["@id"] = id
        if mime_type is not None:
            self["mime-type"] = mime_type
        if filename is not None:
            self["filename"] = filename
        if lastmod_time is not None:
            self["lastmod_time"] = lastmod_time
        if description is not None:
            self["description"] = description
        if data is not None:
            self["data"] = {
                "base64": base64.b64encode(data).decode()
            }

    @property
    def id(self) -> Optional[str]:
        return self['@id']

    @property
    def mime_type(self) -> Optional[str]:
        return self['mime-type']

    @property
    def filename(self) -> Optional[str]:
        return self['filename']

    @property
    def lastmod_time(self) -> Optional[str]:
        return self['lastmod_time']

    @property
    def description(self) -> Optional[str]:
        return self['description']

    @property
    def data(self) -> Optional[bytes]:
        return base64.b64decode(self['data']["base64"])



class AttachesMixin:
    """
    https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0017-attachments
    """

    @property
    def attaches(self) -> List[Attach]:
        if "~attach" in self:
            return self["~attach"]
        else:
            return []

    def add_attach(self, att: Attach):
        if "~attach" not in self:
            self["~attach"] = []
        self["~attach"] += [att]
