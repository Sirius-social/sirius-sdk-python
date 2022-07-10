import warnings
from typing import Optional, List, Union

from sirius_sdk.abstract.bus import AbstractBus
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.abstract.api import APICrypto
from sirius_sdk.agent.wallet.abstract.non_secrets import AbstractNonSecrets
from sirius_sdk.agent.wallet.abstract.cache import AbstractCache
from sirius_sdk.agent.wallet.abstract.did import AbstractDID
from sirius_sdk.messaging import Message
from sirius_sdk.agent.dkms import Ledger, DKMS
from sirius_sdk.agent.listener import Listener
from sirius_sdk.abstract.p2p import Endpoint, Pairwise
from sirius_sdk.agent.microledgers.abstract import AbstractMicroledgerList

from .config import Config
from .core import _current_hub, init, context
from .proxies import DIDProxy, CryptoProxy, MicroledgersProxy, PairwiseProxy, AnonCredsProxy, \
    CacheProxy, NonSecretsProxy
from .coprotocols import CoProtocolThreadedP2P, CoProtocolP2PAnon, CoProtocolP2P, AbstractP2PCoProtocol, \
    CoProtocolThreadedTheirs, open_communication

DID: AbstractDID = DIDProxy()
Crypto: APICrypto = CryptoProxy()
Microledgers: AbstractMicroledgerList = MicroledgersProxy()
PairwiseList: AbstractPairwiseList = PairwiseProxy()
AnonCreds: AnonCredsProxy = AnonCredsProxy()
Cache: AbstractCache = CacheProxy()
NonSecrets: AbstractNonSecrets = NonSecretsProxy()


async def dkms(name: str) -> Optional[DKMS]:
    async with _current_hub().get_agent_connection_lazy() as agent:
        return agent.dkms(name)


async def ledger(name: str) -> Optional[Ledger]:
    """!!! Deprecated Call !!!"""
    warnings.warn('Use sirius_sdk.dkms instead of this call', DeprecationWarning)
    async with _current_hub().get_agent_connection_lazy() as agent:
        return agent.dkms(name)


async def endpoints() -> List[Endpoint]:
    async with _current_hub().get_agent_connection_lazy() as agent:
        return agent.endpoints


async def spawn_coprotocol() -> AbstractBus:
    api = await _current_hub().get_coprotocols()
    bus = await api.spawn_coprotocol()
    return bus


async def subscribe(group_id: str = None) -> Listener:
    async with _current_hub().get_agent_connection_lazy() as agent:
        return await agent.subscribe(group_id=group_id)


async def ping() -> bool:
    async with _current_hub().get_agent_connection_lazy() as agent:
        return await agent.ping()


async def send(
        message: Message, their_vk: Union[List[str], str],
        endpoint: str, my_vk: Optional[str], routing_keys: Optional[List[str]] = None
):
    async with _current_hub().get_agent_connection_lazy() as agent:
        await agent.send(
            message=message, their_vk=their_vk,
            endpoint=endpoint, my_vk=my_vk, routing_keys=routing_keys
        )


async def send_to(message: Message, to: Pairwise):
    async with _current_hub().get_agent_connection_lazy() as agent:
        await agent.send_to(message=message, to=to)


async def generate_qr_code(value: str) -> str:
    async with _current_hub().get_agent_connection_lazy() as agent:
        return await agent.generate_qr_code(value)


async def acquire(resources: List[str], lock_timeout: float, enter_timeout: float = None) -> (bool, List[str]):
    async with _current_hub().get_agent_connection_lazy() as agent:
        kwargs = {'resources': resources, 'lock_timeout': lock_timeout}
        if enter_timeout:
            kwargs['enter_timeout'] = enter_timeout
        return await agent.acquire(**kwargs)


async def release():
    async with _current_hub().get_agent_connection_lazy() as agent:
        await agent.release()
