import os
import uuid
import asyncio

import pytest

from sirius_sdk import Agent, Pairwise
from sirius_sdk.rpc import AddressedTunnel
from sirius_sdk.encryption import create_keypair, bytes_to_b58, P2PConnection
from .helpers import InMemoryChannel, ServerTestSuite, IndyAgent


SERVER_SUITE = None
INDY_AGENT = None


def pytest_configure():
    # Address of TestSuite
    pytest.test_suite_baseurl = os.getenv('TEST_SUITE_BASE_URL') or 'http://localhost'
    pytest.test_suite_overlay_address = 'http://10.0.0.90'
    # Back compatibility testing
    pytest.old_agent_address = os.getenv('INDY_AGENT_BASE_URL') or 'http://127.0.0.1:88'
    pytest.old_agent_overlay_address = 'http://10.0.0.52:8888'
    pytest.old_agent_root = {
        'username': 'root',
        'password': 'root'
    }


@pytest.fixture()
def p2p() -> dict:
    keys_agent = create_keypair(b'000000000000000000000000000AGENT')
    keys_sdk = create_keypair(b'00000000000000000000000000000SDK')
    agent = P2PConnection(
        my_keys=(
            bytes_to_b58(keys_agent[0]),
            bytes_to_b58(keys_agent[1])
        ),
        their_verkey=bytes_to_b58(keys_sdk[0])
    )
    smart_contract = P2PConnection(
        my_keys=(
            bytes_to_b58(keys_sdk[0]),
            bytes_to_b58(keys_sdk[1])
        ),
        their_verkey=bytes_to_b58(keys_agent[0])
    )
    downstream = InMemoryChannel()
    upstream = InMemoryChannel()
    return {
        'agent': {
            'p2p': agent,
            'tunnel': AddressedTunnel('memory://agent->sdk', upstream, downstream, agent)
        },
        'sdk': {
            'p2p': smart_contract,
            'tunnel': AddressedTunnel('memory://sdk->agent', downstream, upstream, smart_contract)
        }
    }


def get_suite_singleton() -> ServerTestSuite:
    global SERVER_SUITE
    if not isinstance(SERVER_SUITE, ServerTestSuite):
        suite = ServerTestSuite()
        asyncio.get_event_loop().run_until_complete(suite.ensure_is_alive())
        SERVER_SUITE = suite
    return SERVER_SUITE


def get_indy_agent_singleton() -> IndyAgent:
    global INDY_AGENT
    if not isinstance(INDY_AGENT, IndyAgent):
        agent = IndyAgent()
        asyncio.get_event_loop().run_until_complete(agent.ensure_is_alive())
        INDY_AGENT = agent
    return INDY_AGENT


def get_agent(name: str) -> Agent:
    params = get_suite_singleton().get_agent_params(name)
    agent = Agent(
        server_address=params['server_address'],
        credentials=params['credentials'],
        p2p=params['p2p'],
        timeout=30,
        name=name
    )
    return agent


@pytest.fixture()
def test_suite() -> ServerTestSuite:
    return get_suite_singleton()


@pytest.fixture()
def indy_agent() -> IndyAgent:
    return get_indy_agent_singleton()


@pytest.fixture()
def agent1() -> Agent:
    return get_agent('agent1')


@pytest.fixture()
def agent2() -> Agent:
    return get_agent('agent2')


@pytest.fixture()
def agent3() -> Agent:
    return get_agent('agent3')


@pytest.fixture()
def agent4() -> Agent:
    return get_agent('agent4')


@pytest.fixture()
def A() -> Agent:
    return get_agent('agent1')


@pytest.fixture()
def B() -> Agent:
    return get_agent('agent2')


@pytest.fixture()
def C() -> Agent:
    return get_agent('agent3')


@pytest.fixture()
def D() -> Agent:
    return get_agent('agent4')


@pytest.fixture()
def ledger_name() -> str:
    return 'Ledger-' + uuid.uuid4().hex


@pytest.fixture()
def default_network() -> str:
    return 'default'


async def get_pairwise(me: Agent, their: Agent):
    suite = get_suite_singleton()
    me_params = suite.get_agent_params(me.name)
    their_params = suite.get_agent_params(their.name)
    me_label, me_entity = list(me_params['entities'].keys())[0], list(me_params['entities'].items())[0][1]
    their_label, their_entity = list(their_params['entities'].keys())[0], list(their_params['entities'].items())[0][1]
    me_endpoint_address = [e for e in me.endpoints if e.routing_keys == []][0].address
    their_endpoint_address = [e for e in their.endpoints if e.routing_keys == []][0].address
    self = me
    for agent, entity_me, entity_their, label_their, endpoint_their in [
        (me, me_entity, their_entity, their_label, their_endpoint_address),
        (their, their_entity, me_entity, me_label, me_endpoint_address)
    ]:
        pairwise = await agent.pairwise_list.load_for_did(their_did=their_entity['did'])
        is_filled = pairwise and pairwise.metadata
        if not is_filled:
            me_ = Pairwise.Me(entity_me['did'], entity_me['verkey'])
            their_ = Pairwise.Their(entity_their['did'], their_label, endpoint_their, entity_their['verkey'])
            metadata = {
                'me': {
                    'did': entity_me['did'],
                    'verkey': entity_me['verkey'],
                    'did_doc': None
                },
                'their': {
                    'did': entity_their['did'],
                    'verkey': entity_their['verkey'],
                    'label': label_their,
                    'endpoint': {
                        'address': endpoint_their,
                        'routing_keys': []
                    },
                    'did_doc': None
                }
            }
            pairwise = Pairwise(me=me_, their=their_, metadata=metadata)
            await agent.wallet.did.store_their_did(entity_their['did'], entity_their['verkey'])
            await agent.pairwise_list.ensure_exists(pairwise)
    pairwise = await self.pairwise_list.load_for_did(their_did=their_entity['did'])
    return pairwise
