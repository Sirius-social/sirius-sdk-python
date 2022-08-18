import base64
import dataclasses
import datetime
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Any, Union

from pytime import pytime
from sirius_sdk.base import Message
from .decorators import *


def parse_datetime(val: str) -> Optional[datetime.datetime]:
    orig_val = val
    if val:
        if val[-1] == 'Z' and len(val.split(' ')) == 2:
            val = val[:-1].replace(' ', 'T')
        for func in [pytime.parse, datetime.datetime.fromisoformat]:
            try:
                return func(val)
            except Exception as e:
                pass
        logging.warning(f'Error while parsing string formatted datetime "{orig_val}"')
        return None
    else:
        return None


class PleaseAckMixin:
    """Explains how one party can request an acknowledgment to and clarify the status of processes.
       - RFC Aries: https://github.com/hyperledger/aries-rfcs/tree/main/features/0317-please-ack
    """

    @property
    def ack_message_id(self) -> Optional[str]:
        return self.get_ack_message_id(self)

    @property
    def please_ack(self) -> bool:
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
    """Definition of the message @id field and the ~thread decorator

      - RFC Aries: https://github.com/hyperledger/aries-rfcs/tree/main/concepts/0008-message-id-and-threading
    """

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
    """Explains the three canonical ways to attach data to an agent message.
      - RFC Aries: https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0017-attachments
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
    """Agents can indicate that an inbound message transmission may also be used as a return route for messages.
       This allows for transports of increased efficiency as well as agents without an inbound route.

      - RFC Aries(v1): https://github.com/hyperledger/aries-rfcs/tree/main/features/0092-transport-return-route
      - RFC DIDComm(v2): https://github.com/decentralized-identity/didcomm-messaging/blob/main/extensions/return_route/main.md
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


class TimingMixin:
    """Explain how timing of agent messages can be communicated and constrained.

      - RFC Aries: https://github.com/hyperledger/aries-rfcs/tree/main/features/0032-message-timing
    """

    @dataclass
    class Timing:
        # The timestamp when the preceding message in this thread (the one that elicited this message as a response)
        # was received. Or, on a dynamically composed forward message, the timestamp when an upstream relay first
        # received the message it's now asking to be forwarded.
        in_time: datetime.datetime = None

        # The timestamp when the message was emitted
        out_time: datetime.datetime = None

        #  Ideally, the decorated message should be processed by the the specified timestamp
        stale_time: datetime.datetime = None

        # The decorated message should be considered invalid or expired if encountered after the specified timestamp
        expires_time: datetime.datetime = None

        # Wait at least this many milliseconds before processing the message
        delay_milli: int = None

        # Wait until this time before processing the message
        wait_until_time: datetime.datetime = None

        def __init__(
                self, in_time: Union[str, datetime.datetime] = None, out_time: Union[str, datetime.datetime] = None,
                stale_time: Union[str, datetime.datetime] = None, expires_time: Union[str, datetime.datetime] = None,
                delay_milli: int = None, wait_until_time: Union[str, datetime.datetime] = None, **kwargs
        ):
            self.in_time = self.__read_value_safe('in_time', in_time)
            self.out_time = self.__read_value_safe('out_time', out_time)
            self.stale_time = self.__read_value_safe('stale_time', stale_time)
            self.expires_time = self.__read_value_safe('expires_time', expires_time)
            self.delay_milli = self.__read_value_safe('delay_milli', delay_milli)
            self.wait_until_time = self.__read_value_safe('wait_until_time', wait_until_time)

        @property
        def is_filled(self) -> bool:
            return any(
                [t is not None for t in (self.in_time, self.out_time, self.stale_time, self.expires_time, self.delay_milli, self.wait_until_time)]
            )

        def to_json(self) -> dict:
            obj = dataclasses.asdict(self)
            return {key: obj[key] for key, value in obj.items() if value is not None}

        def create_from_json(self, js: dict) -> 'TimingMixin.Timing':
            upd_kwargs = {}
            for key, value in js.items():
                safe_val = self.__read_value_safe(key, value)
                upd_kwargs[key] = safe_val
            return dataclasses.replace(self, **upd_kwargs)

        def __read_value_safe(self, name: str, value: Any) -> Any:
            fields = dataclasses.fields(self)
            actual_fields = list(filter(lambda f: f.name == name, fields))
            if actual_fields:
                field = actual_fields[0]
                if field.type == type(value):
                    return value
                else:
                    if field.type == int:
                        if isinstance(value, str) and value.isdigit():
                            return int(value)
                        else:
                            return None
                    elif field.type == datetime.datetime:
                        if isinstance(value, str):
                            return parse_datetime(value)
                        else:
                            return None
                    else:
                        return None
            else:
                return None

    @property
    def timing(self) -> Timing:
        return self.get_timing(self)

    @timing.setter
    def timing(self, value: Timing):
        self.set_timing(self, value)

    @classmethod
    def get_timing(cls, message: Message) -> Optional[Timing]:
        js = message.get(TIMING_DECORATOR, {})
        if js:
            value = TimingMixin.Timing(**js)
            return value if value.is_filled else None
        else:
            return None

    @classmethod
    def set_timing(cls, message: Message, value: Timing):
        js = value.to_json() if value else {}
        if js:
            message[TIMING_DECORATOR] = js
        elif TIMING_DECORATOR in message.keys():
            del message[TIMING_DECORATOR]
