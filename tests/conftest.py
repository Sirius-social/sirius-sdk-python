import os
import uuid
import asyncio

import pytest

from sirius_sdk import Agent
from sirius_sdk.rpc import AddressedTunnel
from sirius_sdk.encryption import create_keypair, bytes_to_b58, P2PConnection
from .helpers import InMemoryChannel, ServerTestSuite, IndyAgent


SERVER_SUITE = None
INDY_AGENT = None


def pytest_configure():
    # Address of TestSuite
    pytest.test_suite_baseurl = os.getenv('TEST_SUITE_BASE_URL') or 'http://agent'
    # Back compatibility testing
    pytest.old_agent_address = os.getenv('INDY_AGENT_BASE_URL') or 'http://10.0.0.52:8888'
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
def ledger_name() -> str:
    return 'Ledger-' + uuid.uuid4().hex
