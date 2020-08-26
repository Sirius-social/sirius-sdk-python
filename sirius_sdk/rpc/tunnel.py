import json

from sirius_sdk.encryption import P2PConnection
from sirius_sdk.base import ReadOnlyChannel, WriteOnlyChannel
from sirius_sdk.messaging import Message
from sirius_sdk.errors.exceptions import *


class AddressedTunnel:
    """Transport abstraction that help build tunnels (p2p pairwise relationships) over channel layer.
    """

    ENC = 'utf-8'

    class Context:
        """Tunnel instance context"""
        def __init__(self):
            # encrypted: flag that represent that last received message was encrypted
            self.encrypted = False

    def __init__(self, address: str, input_: ReadOnlyChannel, output_: WriteOnlyChannel, p2p: P2PConnection):
        """
        :param address: communication address of transport environment on server-side
        :param input_: channel of input stream
        :param output_: channel of output stream
        :param p2p: pairwise connection that configured and prepared outside
        """
        self.__address = address
        self.__input = input_
        self.__output = output_
        self.__p2p = p2p
        self.__context = self.Context()

    @property
    def address(self):
        return self.__address

    @property
    def context(self):
        return self.__context

    async def receive(self, timeout: int=None) -> Message:
        """
        Read message.

        Tunnel allows to receive non-encrypted messages, high-level logic may control message encryption flag
        via context.encrypted field

        :param timeout:timeout in seconds
        :return: received packet
        """
        payload = await self.__input.read(timeout)
        if not isinstance(payload, bytes) and not isinstance(payload, dict):
            raise TypeError('Expected bytes or dict, got {}'.format(type(payload)))
        if isinstance(payload, bytes):
            try:
                payload = json.loads(payload)
            except Exception as e:
                raise SiriusInvalidPayloadStructure("Invalid packed message") from e
        if 'protected' in payload:
            unpacked = self.__p2p.unpack(payload)
            self.__context.encrypted = True
            return Message(unpacked)
        else:
            self.__context.encrypted = False
            return Message(payload)

    async def post(self, message: Message, encrypt: bool=True) -> bool:
        """Write message

        :param message: message to send
        :param encrypt: do encryption
        :return: operation success
        """
        if encrypt:
            payload = self.__p2p.pack(message)
        else:
            payload = message.serialize().encode(self.ENC)
        return await self.__output.write(payload)
