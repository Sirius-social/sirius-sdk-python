from typing import List, Any

import sirius_sdk
from sirius_sdk import AbstractCrypto


class Document:

    def __init__(self):
        self.__content = None

    @property
    def content(self) -> Any:
        return self.__content

    @content.setter
    def content(self, value: Any):
        self.__content = value


class EncryptedDocument(Document):

    def __init__(self, target_verkeys: List[str], my_vk: str = None, crypto: AbstractCrypto = None):
        super().__init__()
        self.__target_verkeys = target_verkeys
        self.__my_vk = my_vk
        self.__crypto = crypto

    async def create_from(self, src: Document):
        self.content = src.content
        await self.decrypt()

    async def encrypt(self) -> bytes:
        crypto = self.__crypto or sirius_sdk.Crypto
        jwe = await crypto.pack_message(
            message=self.content,
            recipient_verkeys=self.__target_verkeys,
            sender_verkey=self.__my_vk
        )
        return jwe

    async def decrypt(self):
        crypto = self.__crypto or sirius_sdk.Crypto
        self.content = await crypto.unpack_message(self.content)
