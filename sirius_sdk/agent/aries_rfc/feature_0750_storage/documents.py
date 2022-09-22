import json
from typing import List, Any, Optional

import sirius_sdk

from .encoding import parse_protected
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
        if isinstance(self.__content, str):
            await stream.write(self.__content.encode())
        else:
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
            self, src: "EncryptedDocument" = None, target_verkeys: List[str] = None, content: Any = None
    ):
        super().__init__()
        self.__target_verkeys = target_verkeys or []
        self.__sender_vk = None
        self.__encrypted = False
        if src:
            self.content = src.content
            self.__encrypted = src.__encrypted
        else:
            if content is not None:
                self.content = content

    @property
    def encrypted(self) -> bool:
        return self.__encrypted

    @encrypted.setter
    def encrypted(self, value: bool):
        self.__encrypted = value

    @property
    def sender_vk(self) -> Optional[str]:
        return self.__sender_vk

    @property
    def target_verkeys(self) -> List[str]:
        return self.__target_verkeys

    @property
    def jwm(self) -> Optional[dict]:
        if self.__encrypted:
            if isinstance(self.content, bytes):
                jwm = json.loads(self.content.decode())
                return jwm
            else:
                return None
        else:
            return None

    async def encrypt(self, my_vk: str = None):
        if not self.__encrypted:
            if not self.__target_verkeys:
                raise RuntimeError(f'Target keys are missing')
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
            protected = parse_protected(self.content)
            unpacked = await sirius_sdk.Crypto.unpack_message(self.content)
            self.content = unpacked['message']
            if isinstance(self.content, str):
                self.content = self.content.encode()
            self.__sender_vk = unpacked.get('sender_verkey')
            self.__target_verkeys = [recip['header']['kid'] for recip in protected['recipients'] if
                                     recip.get('header', {}).get('kid', None) is not None]
            self.__encrypted = False

    def _after_content_changed(self):
        self.__encrypted = False
        self.__sender_vk = None
