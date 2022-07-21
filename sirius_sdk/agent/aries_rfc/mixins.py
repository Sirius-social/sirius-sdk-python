import base64
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List

from sirius_sdk.base import Message
from .decorators import *


class PleaseAckMixin:

    @property
    def ack_message_id(self) -> Optional[str]:
        return self.get_ack_message_id(self)

    @property
    def please_ack(self) -> bool:
        """https://github.com/hyperledger/aries-rfcs/tree/master/features/0317-please-ack"""
        return self.get(PLEASE_ACK_DECORATOR, None) is not None

    @please_ack.setter
    def please_ack(self, flag: bool):
        if flag:
            self[PLEASE_ACK_DECORATOR] = {'message_id': self.id}
        elif PLEASE_ACK_DECORATOR in self:
            del self[PLEASE_ACK_DECORATOR]

    @staticmethod
    def get_ack_message_id(message: Message) -> Optional[str]:
        return message.get(PLEASE_ACK_DECORATOR, {}).get('message_id', None) or message.id


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


class ReturnRouteMixin:
    """
    https://github.com/hyperledger/aries-rfcs/tree/main/features/0092-transport-return-route
    https://github.com/decentralized-identity/didcomm-messaging/blob/main/extensions/return_route/main.md
    """

    class RouteType(Enum):
        NONE = 'none'
        ALL = 'all'
        THREAD = 'thread'

    @property
    def return_route(self) -> RouteType:
        return self.get_return_route(self)

    @return_route.setter
    def return_route(self, value: RouteType):
        self.set_return_route(self, value)

    @classmethod
    def get_return_route(cls, message: Message) -> RouteType:
        value = message.get(TRANSPORT_DECORATOR, {}).get('return_route', None)
        if value is None:
            return cls.RouteType.NONE
        else:
            if value == cls.RouteType.ALL.value:
                return cls.RouteType.ALL
            elif value == cls.RouteType.THREAD.value:
                return cls.RouteType.THREAD
            else:
                return cls.RouteType.NONE

    @classmethod
    def set_return_route(cls, message: Message, transport: RouteType):
        message[TRANSPORT_DECORATOR] = {
            'return_route': transport.value
        }
