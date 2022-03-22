r"""DIDComm Transports are simplex: they only transfer messages from sender to receiver,
using the endpoint present in the receiver's DID Document.
This extension enables bi-directional communication on the same transports, even when one party has no public endpoint.
Messages can flow back in response to inbound messages over the same connection.
This is particularly useful for communication between agents that are unable to provide routable endpoints
(such as mobile phones or agents inside a firewall) and their mediators.

Details: https://github.com/decentralized-identity/didcomm-messaging/blob/master/extensions/return_route/main.md
"""
from .headers import HEADER_NAME, extract_value, RouteType
from .const import URI_QUEUE_TRANSPORT


__all__ = ["extract_value", "HEADER_NAME", "RouteType", "URI_QUEUE_TRANSPORT"]
