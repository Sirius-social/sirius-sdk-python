import os
import uuid
import asyncio
from typing import Tuple, Dict
from os.path import abspath, relpath, dirname, join as path_join

import pytest

import sirius_sdk
from sirius_sdk import Agent, Pairwise, APICrypto
from sirius_sdk.hub.mediator import Mediator
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
        name=name
    )
    return agent


def get_agent_config(name: str) -> Dict:
    params = get_suite_singleton().get_agent_params(name)
    return {
        'server_uri': params['server_address'],
        'credentials': params['credentials'],
        'p2p': params['p2p']
    }


@pytest.fixture()
def test_suite() -> ServerTestSuite:
    return get_suite_singleton()


@pytest.fixture()
def prover_master_secret_name() -> str:
    return 'prover_master_secret_name'


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
def config_a() -> Dict:
    return get_agent_config('agent1')


@pytest.fixture()
def config_b() -> Dict:
    return get_agent_config('agent2')


@pytest.fixture()
def config_c() -> Dict:
    return get_agent_config('agent3')


@pytest.fixture()
def config_d() -> Dict:
    return get_agent_config('agent4')


@pytest.fixture()
def ledger_name() -> str:
    return 'Ledger-' + uuid.uuid4().hex


@pytest.fixture()
def ledger_names() -> list:
    return ['Ledger-' + uuid.uuid4().hex for n in range(2)]


@pytest.fixture()
def default_network() -> str:
    return 'default'


@pytest.fixture()
def mediator_invitation() -> dict:
    return {
        '@type': 'https://didcomm.org/connections/1.0/invitation',
        '@id': uuid.uuid4().hex,
        'label': 'Testable-Mediator',
        'recipientKeys': ['F5BERxEyX6uDhgXCbizxJB1z3SGnjHbjfzwuTytuK4r5'],
        'serviceEndpoint': 'ws://localhost:8000/ws',
        'routingKeys': [],
    }


async def get_pairwise(me: Agent, their: Agent) -> sirius_sdk.Pairwise:
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


async def get_pairwise2(me: Tuple[Dict, str], their: Tuple[Dict, str]) -> sirius_sdk.Pairwise:
    server_uri1 = me[0].get('server_address') or me[0].get('server_uri')
    agent_me = Agent(
        server_address=server_uri1,
        credentials=me[0]['credentials'],
        p2p=me[0]['p2p'],
        name=me[1]
    )
    server_uri2 = their[0].get('server_address') or their[0].get('server_uri')
    agent_their = Agent(
        server_address=server_uri2,
        credentials=their[0]['credentials'],
        p2p=their[0]['p2p'],
        name=their[1]
    )
    await agent_me.open()
    await agent_their.open()
    try:
        p2p = await get_pairwise(agent_me, agent_their)
        return p2p
    finally:
        await agent_me.close()
        await agent_their.close()


async def get_pairwise3(me: Dict, their: Dict) -> sirius_sdk.Pairwise:
    suite = get_suite_singleton()
    me_name = None
    for name, config in suite.metadata.items():
        cred1 = me['credentials'].decode() if isinstance(me['credentials'], bytes) else me['credentials']
        cred2 = config['credentials'].decode() if isinstance(config['credentials'], bytes) else config['credentials']
        if cred1 == cred2:
            me_name = name
    if me_name is None:
        raise RuntimeError('Not found test-suite agent name')
    their_name = None
    for name, config in suite.metadata.items():
        cred1 = their['credentials'].decode() if isinstance(their['credentials'], bytes) else their['credentials']
        cred2 = config['credentials'].decode() if isinstance(config['credentials'], bytes) else config['credentials']
        if cred1 == cred2:
            their_name = name
    if their_name is None:
        raise RuntimeError('Not found test-suite agent name')
    p2p = await get_pairwise2(me=(me, me_name), their=(their, their_name))
    return p2p


def create_mediator_instance(mediator_invitation: dict, my_verkey: str, routing_keys: list = None) -> Mediator:
    instance = Mediator(
        uri=mediator_invitation['serviceEndpoint'],
        my_verkey=my_verkey,
        mediator_verkey=mediator_invitation['recipientKeys'][0],
        routing_keys=routing_keys
    )
    return instance


@pytest.fixture()
def files_dir():
    cur = abspath(relpath(dirname(__file__)))
    return path_join(cur, 'files')
