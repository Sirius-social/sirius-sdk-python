from typing import Any, Optional, List

import pytest

import sirius_sdk
from sirius_sdk.abstract.bus import AbstractBus
from sirius_sdk.abstract.api import APICoProtocols
from sirius_sdk import APICrypto

from tests.helpers import ServerTestSuite


class OverriddenMethodCalled(RuntimeError):
    pass


class OverriddenBus(AbstractBus):

    async def subscribe(self, thid: str) -> bool:
        raise OverriddenMethodCalled

    async def subscribe_ext(self, sender_vk: List[str], recipient_vk: List[str], protocols: List[str]) -> (bool, List[str]):
        raise OverriddenMethodCalled

    async def unsubscribe(self, thid: str):
        raise OverriddenMethodCalled

    async def unsubscribe_ext(self, thids: List[str]):
        raise OverriddenMethodCalled

    async def publish(self, thid: str, payload: bytes) -> int:
        raise OverriddenMethodCalled

    async def publish_ext(self, binding_ids: List[str], payload: bytes) -> int:
        raise OverriddenMethodCalled

    async def get_event(self, timeout: float = None) -> AbstractBus.BytesEvent:
        raise OverriddenMethodCalled

    async def get_message(self, timeout: float = None) -> AbstractBus.MessageEvent:
        raise OverriddenMethodCalled

    async def abort(self):
        raise OverriddenMethodCalled


class OverriddenCoprotocols(APICoProtocols):

    async def spawn_coprotocol(self) -> AbstractBus:
        return OverriddenBus()


class OverriddenCrypto(APICrypto):

    async def create_key(self, seed: str = None, crypto_type: str = None) -> str:
        return 'KEY'

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        raise NotImplemented

    async def get_key_metadata(self, verkey: str) -> Optional[dict]:
        raise NotImplemented

    async def crypto_sign(self, signer_vk: str, msg: bytes) -> bytes:
        raise NotImplemented

    async def crypto_verify(self, signer_vk: str, msg: bytes, signature: bytes) -> bool:
        raise NotImplemented

    async def anon_crypt(self, recipient_vk: str, msg: bytes) -> bytes:
        raise NotImplemented

    async def anon_decrypt(self, recipient_vk: str, encrypted_msg: bytes) -> bytes:
        raise NotImplemented

    async def pack_message(self, message: Any, recipient_verkeys: list, sender_verkey: str = None) -> bytes:
        raise NotImplemented

    async def unpack_message(self, jwe: bytes) -> dict:
        raise NotImplemented


@pytest.mark.asyncio
async def test_config_cloud(test_suite: ServerTestSuite):
    params = test_suite.get_agent_params('agent3')
    cfg = sirius_sdk.Config().setup_cloud(params['server_address'], params['credentials'], params['p2p'])
    async with sirius_sdk.context(cfg):
        test = await sirius_sdk.DID.list_my_dids_with_meta()
        assert type(test) is list


@pytest.mark.asyncio
async def test_override_crypto():
    cfg = sirius_sdk.Config().override_crypto(dependency=OverriddenCrypto())
    async with sirius_sdk.context(cfg):
        key = await sirius_sdk.Crypto.create_key()
        assert key == 'KEY'


@pytest.mark.asyncio
async def test_override_coprotocols():
    cfg = sirius_sdk.Config().override_coprotocols(dependency=OverriddenCoprotocols())
    async with sirius_sdk.context(cfg):
        bus = await sirius_sdk.spawn_coprotocol()
        with pytest.raises(OverriddenMethodCalled):
            await bus.subscribe('thid')
