from typing import Any, Optional

import pytest

import sirius_sdk
from sirius_sdk.agent.wallet.abstract import AbstractCrypto

from .helpers import ServerTestSuite


class OverriddenCrypto(AbstractCrypto):

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
