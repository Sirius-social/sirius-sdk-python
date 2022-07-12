import asyncio

import pytest

import sirius_sdk
from sirius_sdk import Agent, TheirEndpoint, Pairwise
import sirius_sdk.hub.coprotocols_bus
from sirius_sdk.errors.exceptions import *
from tests.conftest import get_pairwise
from sirius_sdk.messaging import Message
from tests.helpers import run_coroutines, LocalCryptoManager, LocalDIDManager
from sirius_sdk.hub.defaults.default_crypto import DefaultCryptoService

from .helpers import MSG_LOG, check_msg_log, TEST_MSG_TYPES
from .test_cloud_agent import routine1, routine2


async def routine1(
        co: sirius_sdk.hub.coprotocols_bus.AbstractP2PCoProtocol,
        cfg: sirius_sdk.Config, **kwargs
):
    async with sirius_sdk.context(cfg):
        first_req = Message({
            '@type': TEST_MSG_TYPES[0],
            'content': 'Request1'
        })
        MSG_LOG.append(first_req)
        print('#2')
        ok, resp1 = await co.switch(message=first_req)
        print('#2')
        assert ok is True
        MSG_LOG.append(resp1)
        ok, resp2 = await co.switch(
            message=Message({
                '@type': TEST_MSG_TYPES[2],
                'content': 'Request2'
            })
        )
        assert ok is True
        MSG_LOG.append(resp2)


async def routine2(
        co: sirius_sdk.hub.coprotocols_bus.AbstractP2PCoProtocol,
        cfg: sirius_sdk.Config, **kwargs
):
    async with sirius_sdk.context(cfg):
        await asyncio.sleep(1)
        print('#1')
        ok, resp1 = await co.switch(
            message=Message({
                '@type': TEST_MSG_TYPES[1],
                'content': 'Response1'
            })
        )
        print('#2')
        assert ok is True
        MSG_LOG.append(resp1)
        await co.send(
            message=Message({
                '@type': TEST_MSG_TYPES[3],
                'content': 'End'
            })
        )


@pytest.mark.asyncio
async def test__their_endpoint_coprotocol(mediator_uri: str, mediator_verkey: str):

    crypto1 = LocalCryptoManager()
    crypto2 = LocalCryptoManager()
    my_vk1 = await crypto1.create_key(seed='0'*32)
    my_vk2 = await crypto2.create_key(seed='1'*32)
    cfg1 = sirius_sdk.Config().setup_mediator(mediator_uri, my_vk1, mediator_verkey).\
        override_crypto(dependency=crypto1).override_did(dependency=LocalDIDManager())
    cfg2 = sirius_sdk.Config().setup_mediator(mediator_uri, my_vk2, mediator_verkey).\
        override_crypto(dependency=crypto2).override_did(dependency=LocalDIDManager())
    print('#')

    async with sirius_sdk.context(cfg1):
        agent1_endpoint = [e for e in await sirius_sdk.endpoints() if e.is_default][0].address
    print('')
    async with sirius_sdk.context(cfg2):
        agent2_endpoint = [e for e in await sirius_sdk.endpoints() if e.is_default][0].address

    # FIRE!!!
    their1 = TheirEndpoint(agent2_endpoint, my_vk2)
    their2 = TheirEndpoint(agent1_endpoint, my_vk1)
    co1 = sirius_sdk.hub.coprotocols_bus.CoProtocolP2PAnon(my_vk1, their1, ['test_protocol'])
    co2 = sirius_sdk.hub.coprotocols_bus.CoProtocolP2PAnon(my_vk2, their2, ['test_protocol'])
    MSG_LOG.clear()
    await run_coroutines(
        routine1(co1, cfg1),
        routine2(co2, cfg2),
        timeout=50
    )
    check_msg_log()
