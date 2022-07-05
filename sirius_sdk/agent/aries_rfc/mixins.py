import base64
from dataclasses import dataclass
from typing import Optional, List

from sirius_sdk.base import Message
from .decorators import *


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

    @dataclass
    class Thread:
        thid: str = None
        pthid: str = None
        sender_order: int = None
        received_orders: dict = None

        @property
        def is_filled(self) -> bool:
            return self.thid is not None or \
                   self.pthid is not None or \
                   self.sender_order is not None or \
                   self.received_orders is not None

    @property
    def thread_id(self) -> Optional[str]:
        return self.get(THREAD_DECORATOR, {}).get('thid', None)

    @thread_id.setter
    def thread_id(self, thid: str):
        thread = self.get(THREAD_DECORATOR, {})
        thread['thid'] = thid
        self[THREAD_DECORATOR] = thread

    @property
    def thread(self) -> Optional[Thread]:
        return self.get_thread(self)

    @thread.setter
    def thread(self, value: Thread = None):
        self.set_thread(self, value)

    @staticmethod
    def get_thread(message: Message) -> Optional[Thread]:
        d = message.get(THREAD_DECORATOR, {})
        thid = d.get('thid', None)
        pthid = d.get('pthid', None)
        if 'sender_order' in d:
            try:
                sender_order = int(d['sender_order'])
            except ValueError:
                sender_order = None
        else:
            sender_order = None
        if 'received_orders' in d:
            received_orders = d['received_orders']
            if not isinstance(received_orders, dict):
                received_orders = None
        else:
            received_orders = None

        thread = ThreadMixin.Thread(
            thid=thid, pthid=pthid, sender_order=sender_order, received_orders=received_orders
        )
        if thread.is_filled:
            return thread
        else:
            return None

    @staticmethod
    def set_thread(message: Message, value: Thread = None):
        if value is not None and value.is_filled:
            d = {}
            if value.thid:
                d['thid'] = value.thid
            if value.pthid:
                d['pthid'] = value.pthid
            if value.sender_order is not None:
                d['sender_order'] = value.sender_order
            if value.received_orders is not None:
                d['received_orders'] = value.received_orders
            message[THREAD_DECORATOR] = d
        else:
            if THREAD_DECORATOR in self:
                del message[THREAD_DECORATOR]


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
