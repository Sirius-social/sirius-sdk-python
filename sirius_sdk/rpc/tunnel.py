from typing import Any

from ..encryption import P2PConnection
from ..base import ReadOnlyChannel, WriteOnlyChannel


class AddressedTunnel(ReadOnlyChannel, WriteOnlyChannel):

    def __init__(self, address: str, input_: ReadOnlyChannel, output_: WriteOnlyChannel, p2p: P2PConnection):
        self.__address = address
        self.__input = input_
        self.__output = output_
        self.__p2p = p2p

    @property
    def address(self):
        return self.__address

    async def read(self, timeout: int=None) -> Any:
        enc_message = await self.__input.read(timeout)
        unpacked = self.__p2p.unpack(enc_message)
        return unpacked

    async def write(self, message: dict) -> bool:
        enc_message = self.__p2p.pack(message)
        return await self.__output.write(enc_message)
