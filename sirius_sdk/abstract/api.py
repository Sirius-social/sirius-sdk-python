from abc import ABC, abstractmethod
from typing import Optional, List, Union

from sirius_sdk.agent.dkms import DKMS
from sirius_sdk.messaging import Message

from .bus import AbstractBus
from .p2p import Endpoint, Pairwise
from .listener import AbstractListener


class API(ABC):

    @abstractmethod
    async def spawn_coprotocol(self) -> AbstractBus:
        raise NotImplemented

    @abstractmethod
    def dkms(self, name: str) -> Optional[DKMS]:
        raise NotImplemented

    @abstractmethod
    async def endpoints(self) -> List[Endpoint]:
        raise NotImplemented

    @abstractmethod
    async def subscribe(self, group_id: str = None) -> AbstractListener:
        raise NotImplemented

    @abstractmethod
    async def send(
            self, message: Message, their_vk: Union[List[str], str],
            endpoint: str, my_vk: Optional[str], routing_keys: Optional[List[str]] = None
    ):
        raise NotImplemented

    @abstractmethod
    async def send_to(self, message: Message, to: Pairwise):
        raise NotImplemented

    @abstractmethod
    async def generate_qr_code(self, value: str) -> str:
        raise NotImplemented

    @abstractmethod
    async def acquire(self, resources: List[str], lock_timeout: float, enter_timeout: float = None) -> (bool, List[str]):
        raise NotImplemented

    @abstractmethod
    async def release(self):
        raise NotImplemented
