"""
The Queue Transport is a special form of transport where messages are held at the sender for pickup by the recipient.
This is useful in conditions where the recipient does not have a reliable endpoint available for message reception.

Details: https://github.com/decentralized-identity/didcomm-messaging/blob/master/extensions/return_route/main.md#queue-transport
"""
URI_QUEUE_TRANSPORT = 'didcomm:transport/queue'
