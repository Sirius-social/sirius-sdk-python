import json
import uuid
import asyncio
import datetime
from collections import OrderedDict
from dataclasses import dataclass
from typing import Union, Optional, List, OrderedDict as OrderedDictAlias

from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage, VALID_DOC_URI, AriesProblemReport


class BasePickUpMessage(AriesProtocolMessage, metaclass=RegisterMessage):
    """Aries 0212 Pickup Protocol

    https://github.com/hyperledger/aries-rfcs/tree/main/features/0212-pickup

    """
    DOC_URI = VALID_DOC_URI[0]
    PROTOCOL = 'messagepickup'

    @dataclass
    class BatchedMessage:
        msg_id: str = None
        message: Union[dict, str] = None

    @property
    def return_route(self) -> Optional[str]:
        return self.get('~transport', {}).get('return_route', None)

    @return_route.setter
    def return_route(self, value: str):
        transport = self.get('~transport', {})
        transport['return_route'] = value
        self['~transport'] = transport


class PickUpStatusRequest(BasePickUpMessage):
    NAME = 'status-request'


class PickUpStatusResponse(BasePickUpMessage):
    NAME = 'status'

    def __init__(
            self,
            message_count: int = None,
            duration_limit: int = None, last_added_time: str = None,
            last_delivered_time: str = None, last_removed_time: str = None,
            *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if message_count is not None:
            self['message_count'] = message_count
        if duration_limit is not None:
            self['duration_limit'] = duration_limit
        if last_added_time is not None:
            self['last_added_time'] = last_added_time
        if last_delivered_time is not None:
            self['last_delivered_time'] = last_delivered_time
        if last_removed_time is not None:
            self['last_removed_time'] = last_removed_time

    """Required Status Properties:"""
    @property
    def message_count(self) -> Optional[int]:
        # The number of messages in the queue
        return self.get('message_count', None)

    """Optional Status Properties"""
    @property
    def duration_limit(self) -> Optional[int]:
        # The maximum duration in seconds that a message may stay in the queue
        # without being delivered (may be zero for no limit)
        return self.get('duration_limit', None)

    def last_added_time(self) -> Optional[str]:
        # A timestamp representing the last time a message was added to the queue
        return self.get('last_added_time', None)

    @property
    def last_removed_time(self) -> Optional[str]:
        # A timestamp representing the last time one or more messages was removed from the queue
        return self.get('last_removed_time', None)


class PickUpBatchRequest(BasePickUpMessage):
    NAME = 'batch-pickup'

    def __init__(self, batch_size: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if batch_size is not None:
            self['batch_size'] = batch_size

    @property
    def batch_size(self) -> Optional[str]:
        return self.get('batch_size', None)


class PickUpBatchResponse(BasePickUpMessage):

    NAME = 'batch'

    def __init__(self, messages: List[BasePickUpMessage.BatchedMessage] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if messages is not None:
            attach = []
            for msg in messages:
                attach.append({
                    '@id': msg.msg_id,
                    'message': msg.message
                })
            self['messages~attach'] = attach

    @property
    def messages(self) -> List[BasePickUpMessage.BatchedMessage]:
        messages = []
        for attach in self.get('messages~attach', []):
            message = BasePickUpMessage.BatchedMessage(
                msg_id=attach.get('@id', None),
                message=attach.get('message', None)
            )
            messages.append(message)
        return messages


class PickUpListRequest(BasePickUpMessage):
    NAME = 'list-pickup'

    def __init__(self, message_ids: List[str] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if message_ids is not None:
            self['message_ids'] = message_ids

    @property
    def message_ids(self) -> List[str]:
        return self.get('message_ids', [])


class PickUpListResponse(BasePickUpMessage):
    NAME = 'list-response'

    def __init__(self, messages: List[BasePickUpMessage.BatchedMessage] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if messages is not None:
            attach = []
            for msg in messages:
                attach.append({
                    '@id': msg.msg_id,
                    'message': msg.message
                })
            self['messages~attach'] = attach

    @property
    def messages(self) -> List[BasePickUpMessage.BatchedMessage]:
        messages = []
        for attach in self.get('messages~attach', []):
            message = BasePickUpMessage.BatchedMessage(
                msg_id=attach.get('@id', None),
                message=attach.get('message', None)
            )
            messages.append(message)
        return messages


class PickUpNoop(BasePickUpMessage):
    NAME = 'noop'


class PickUpProblemReport(AriesProblemReport, metaclass=RegisterMessage):
    DOC_URI = BasePickUpMessage.DOC_URI
    PROTOCOL = BasePickUpMessage.PROTOCOL

    # Problem Codes
    PROBLEM_CODE_EMPTY = 'empty_queue'
    PROBLEM_CODE_INVALID_REQ = 'invalid_request'
    PROBLEM_CODE_TIMEOUT_OCCURRED = 'timeout_occurred'
