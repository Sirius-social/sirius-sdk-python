import pytest

from sirius_sdk.rpc import AddressedTunnel
from sirius_sdk.encryption import create_keypair, bytes_to_b58, P2PConnection
from .helpers import InMemoryChannel


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
