import json
from typing import Any

from ..encryption import P2PConnection
from ..base import ReadOnlyChannel, WriteOnlyChannel


class AddressedTunnel(ReadOnlyChannel, WriteOnlyChannel):

    def __init__(self, address: str, input_: ReadOnlyChannel, output_: WriteOnlyChannel, p2p: P2PConnection):
        self.__address = address
        self.__input = input_
        self.__output = output_
        self.__p2p = p2p
        self.__context = {
            'encrypted': False
        }

    @property
    def address(self):
        return self.__address

    @property
    def context(self):
        return self.__context

    async def read(self, timeout: int=None) -> Any:
        payload = await self.__input.read(timeout)
        if not isinstance(payload, bytes) and not isinstance(payload, dict):
            raise TypeError('Expected bytes or dict, got {}'.format(type(payload)))
        if isinstance(payload, bytes):
            try:
                payload = json.loads(payload)
            except Exception as e:
                raise ValueError("Invalid packed message") from e
        if 'protected' in payload:
            unpacked = self.__p2p.unpack(payload)
            self.__context['encrypted'] = True
            return unpacked
        else:
            self.__context['encrypted'] = False
            return payload

    async def write(self, message: dict) -> bool:
        enc_message = self.__p2p.pack(message)
        return await self.__output.write(enc_message)
