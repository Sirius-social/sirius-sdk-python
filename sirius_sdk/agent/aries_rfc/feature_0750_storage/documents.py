import json
from typing import List, Any, Optional

import sirius_sdk
from sirius_sdk import APICrypto

from .streams import AbstractWriteOnlyStream, AbstractReadOnlyStream


class Document:

    def __init__(self):
        self.__content = None

    @property
    def content(self) -> Any:
        return self.__content

    @content.setter
    def content(self, value: Any):
        self._before_content_change()
        self.__content = value
        self._after_content_changed()

    async def save(self, stream: AbstractWriteOnlyStream):
        await stream.truncate()
        await stream.write(self.__content)

    async def load(self, stream: AbstractReadOnlyStream):
        await stream.seek_to_chunk(0)
        self.__content = await stream.read()

    def _before_content_change(self):
        pass

    def _after_content_changed(self):
        pass


class EncryptedDocument(Document):

    def __init__(
            self, src: "EncryptedDocument" = None, target_verkeys: List[str] = None
    ):
        super().__init__()
        self.__target_verkeys = target_verkeys or []
        self.__sender_vk = None
        self.__encrypted = False
        if src:
            self.content = src.content
            self.__encrypted = src.__encrypted

    @property
    def encrypted(self) -> bool:
        return self.__encrypted

    @encrypted.setter
    def encrypted(self, value: bool):
        self.__encrypted = value

    @property
    def sender_vk(self) -> Optional[str]:
        return self.__sender_vk

    async def encrypt(self, my_vk: str = None):
        if not self.__encrypted:
            if isinstance(self.content, bytes):
                content = self.content.decode()
            else:
                content = self.content
            self.content = await sirius_sdk.Crypto.pack_message(
                message=content,
                recipient_verkeys=self.__target_verkeys,
                sender_verkey=my_vk
            )
            self.__encrypted = True

    async def decrypt(self):
        if self.__encrypted:
            unpacked = await sirius_sdk.Crypto.unpack_message(self.content)
            self.content = unpacked['message'].encode()
            self.__sender_vk = unpacked.get('sender_verkey')
            self.__encrypted = False

    def _after_content_changed(self):
        self.__encrypted = False
        self.__sender_vk = None
