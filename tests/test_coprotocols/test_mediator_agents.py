import asyncio
import uuid

import pytest

import sirius_sdk
from sirius_sdk import Agent, TheirEndpoint, Pairwise
import sirius_sdk.hub.coprotocols
from sirius_sdk.errors.exceptions import *
from tests.conftest import get_pairwise
from sirius_sdk.messaging import Message
from tests.helpers import run_coroutines, LocalCryptoManager, LocalDIDManager
from sirius_sdk.hub.defaults.default_crypto import DefaultCryptoService

from .helpers import MSG_LOG, check_msg_log, TEST_MSG_TYPES


async def routine1(
        co: sirius_sdk.hub.coprotocols.AbstractP2PCoProtocol,
        cfg: sirius_sdk.Config, **kwargs
):
    async with sirius_sdk.context(cfg):
        try:
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
        except Exception as e:
            raise


async def routine2(
        co: sirius_sdk.hub.coprotocols.AbstractP2PCoProtocol,
        cfg: sirius_sdk.Config, **kwargs
):
    async with sirius_sdk.context(cfg):
        try:
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
            print('')
        except Exception as e:
            raise


@pytest.mark.skip
@pytest.mark.asyncio
async def test__their_endpoint_coprotocol(mediator_uri: str, mediator_verkey: str):

    crypto1 = LocalCryptoManager()
    crypto2 = LocalCryptoManager()
    my_vk1 = await crypto1.create_key()
    my_vk2 = await crypto2.create_key()
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
    co1 = sirius_sdk.hub.coprotocols.CoProtocolP2PAnon(my_vk1, their1, ['test_protocol'])
    co2 = sirius_sdk.hub.coprotocols.CoProtocolP2PAnon(my_vk2, their2, ['test_protocol'])
    MSG_LOG.clear()
    await run_coroutines(
        routine1(co1, cfg1),
        routine2(co2, cfg2),
        timeout=15
    )
    check_msg_log()


@pytest.mark.skip
@pytest.mark.asyncio
async def test__threadbased_coprotocol(mediator_uri: str, mediator_verkey: str):
    crypto1 = LocalCryptoManager()
    crypto2 = LocalCryptoManager()
    my_vk1 = await crypto1.create_key()
    my_vk2 = await crypto2.create_key()
    cfg1 = sirius_sdk.Config().setup_mediator(mediator_uri, my_vk1, mediator_verkey). \
        override_crypto(dependency=crypto1).override_did(dependency=LocalDIDManager(crypto1))
    cfg2 = sirius_sdk.Config().setup_mediator(mediator_uri, my_vk2, mediator_verkey). \
        override_crypto(dependency=crypto2).override_did(dependency=LocalDIDManager(crypto2))

    async with sirius_sdk.context(cfg1):
        # Get endpoints
        agent1_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
        # Init pairwise list #1
        did1, verkey1 = await sirius_sdk.DID.create_and_store_my_did()

    async with sirius_sdk.context(cfg2):
        # Get endpoints
        agent2_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0].address
        # Init pairwise list #1
        did2, verkey2 = await sirius_sdk.DID.create_and_store_my_did()

    async with sirius_sdk.context(cfg1):
        await sirius_sdk.DID.store_their_did(did2, verkey2)
    async with sirius_sdk.context(cfg2):
        await sirius_sdk.DID.store_their_did(did1, verkey1)

    # Init pairwise list #2
    pairwise1 = Pairwise(
        me=Pairwise.Me(
            did=did1,
            verkey=verkey1
        ),
        their=Pairwise.Their(
            did=did2,
            label='Label-2',
            endpoint=agent2_endpoint,
            verkey=verkey2
        )
    )
    pairwise2 = Pairwise(
        me=Pairwise.Me(
            did=did2,
            verkey=verkey2
        ),
        their=Pairwise.Their(
            did=did1,
            label='Label-1',
            endpoint=agent1_endpoint,
            verkey=verkey1
        )
    )

    thread_id = 'threadbased_coprotocol-' + uuid.uuid4().hex
    co1 = sirius_sdk.hub.coprotocols.CoProtocolThreadedP2P(thread_id, pairwise1)
    co2 = sirius_sdk.hub.coprotocols.CoProtocolThreadedP2P(thread_id, pairwise2)
    MSG_LOG.clear()
    await run_coroutines(
        routine1(co1, cfg1),
        routine2(co2, cfg2),
        timeout=15
    )
    check_msg_log()
