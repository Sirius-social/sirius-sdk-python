r"""This extension adds a new header in DIDComm messages: return_route. When a message is received with this header,
use of the connection to return messages should be adjusted according to the value presented.

Details: https://github.com/decentralized-identity/didcomm-messaging/blob/master/extensions/return_route/main.md#return-route-header
"""
import logging
from enum import Enum
from typing import Union, Optional


class RouteType(Enum):
    # Default. No messages should be returned over this connection. Default value.
    NONE = 'none'

    # Send all messages for this DID over the connection.
    ALL = 'all'

    # Send all messages matching the DID and thread specified in the return_route_thread attribute.
    THREAD = 'thread'


HEADER_NAME = 'return_route'


def extract_value(headers: Union[dict, list]) -> RouteType:
    """For HTTP transports, the presence of this message decorator indicates
    that the receiving agent MAY hold onto the connection and use it to return messages as designated.
    HTTP transports will only be able to receive at most one message at a time.
    Websocket transports are capable of receiving multiple messages over a single connection.

    :param headers: http headers of the transport
    """
    if type(headers) is dict:
        headers = list(headers.items())
    if type(headers) is not list:
        logging.warning('Unexpected headers type')
        return RouteType.NONE
    for item in headers:
        if type(item) is tuple and len(item) == 2:
            name, value = item
            if type(name) is bytes:
                name = name.decode()
            if name == HEADER_NAME:
                if type(value) is bytes:
                    value = value.decode()
                if value == RouteType.ALL.value:
                    return RouteType.ALL
                elif value == RouteType.THREAD.value:
                    return RouteType.THREAD
                else:
                    return RouteType.NONE
        else:
            logging.warning('Unexpected header type')
    return RouteType.NONE
