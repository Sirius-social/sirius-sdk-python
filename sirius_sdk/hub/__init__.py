import warnings
from typing import Optional, List, Union, Tuple

from sirius_sdk.abstract.bus import AbstractBus
from sirius_sdk.abstract.batching import RoutingBatch
from sirius_sdk.abstract.listener import AbstractListener
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.abstract.api import APICrypto
from sirius_sdk.agent.wallet.abstract.non_secrets import AbstractNonSecrets
from sirius_sdk.agent.wallet.abstract.cache import AbstractCache
from sirius_sdk.agent.wallet.abstract.did import AbstractDID
from sirius_sdk.messaging import Message
from sirius_sdk.agent.dkms import Ledger, DKMS
from sirius_sdk.abstract.p2p import Endpoint, Pairwise
from sirius_sdk.agent.microledgers.abstract import AbstractMicroledgerList
from sirius_sdk.errors.exceptions import SiriusInitializationError

from .config import Config
from .core import _current_hub, init, context
from .proxies import DIDProxy, CryptoProxy, MicroledgersProxy, PairwiseProxy, AnonCredsProxy, \
    CacheProxy, NonSecretsProxy
from .coprotocols import CoProtocolThreadedP2P, CoProtocolP2PAnon, CoProtocolP2P, AbstractP2PCoProtocol, \
    CoProtocolThreadedTheirs, open_communication, prepare_response

DID: AbstractDID = DIDProxy()
Crypto: APICrypto = CryptoProxy()
Microledgers: AbstractMicroledgerList = MicroledgersProxy()
PairwiseList: AbstractPairwiseList = PairwiseProxy()
AnonCreds: AnonCredsProxy = AnonCredsProxy()
Cache: AbstractCache = CacheProxy()
NonSecrets: AbstractNonSecrets = NonSecretsProxy()


async def dkms(name: str) -> Optional[DKMS]:
    api = await _current_hub().get_networks()
    if api is None:
        raise SiriusInitializationError('Configure APINetworks via "Config.override_networks(...)"')
    return api.dkms(name)


async def ledger(name: str) -> Optional[Ledger]:
    """!!! Deprecated Call !!!"""
    warnings.warn('Use sirius_sdk.dkms instead of this call', DeprecationWarning)
    return await dkms(name)


async def spawn_coprotocol() -> AbstractBus:
    api = await _current_hub().get_coprotocols()
    if api is None:
        raise SiriusInitializationError('Configure APICoProtocols via "Config.override_coprotocols(...)"')
    bus = await api.spawn_coprotocol()
    return bus


async def endpoints() -> List[Endpoint]:
    api = await _current_hub().get_router()
    if api is None:
        raise SiriusInitializationError('Configure APIRouter via "Config.override_router(...)"')
    return await api.get_endpoints()


async def subscribe(group_id: str = None) -> AbstractListener:
    api = await _current_hub().get_router()
    if api is None:
        raise SiriusInitializationError('Configure APIRouter via "Config.override_router(...)"')
    return await api.subscribe(group_id=group_id)


async def ping() -> bool:
    success = await _current_hub().ping()
    return success


async def send(
        message: Message, their_vk: Union[List[str], str],
        endpoint: str, my_vk: Optional[str], routing_keys: Optional[List[str]] = None
):
    api = await _current_hub().get_transport()
    if api is None:
        raise SiriusInitializationError('Configure APITransport via "Config.override_transport(...)"')
    await api.send(
        message=message, their_vk=their_vk,
        endpoint=endpoint, my_vk=my_vk, routing_keys=routing_keys
    )


async def send_to(message: Message, to: Pairwise):
    api = await _current_hub().get_transport()
    if api is None:
        raise SiriusInitializationError('Configure APITransport via "Config.override_transport(...)"')
    await api.send_to(message=message, to=to)


async def send_batched(message: Message, batches: List[RoutingBatch]) -> List[Tuple[bool, str]]:
    api = await _current_hub().get_transport()
    if api is None:
        raise SiriusInitializationError('Configure APITransport via "Config.override_transport(...)"')
    results = await api.send_batched(message, batches)
    return results


async def generate_qr_code(value: str) -> str:
    api = await _current_hub().get_contents()
    if api is None:
        raise SiriusInitializationError('Configure APIContents via "Config.override_contents(...)"')
    url = await api.generate_qr_code(value)
    return url


async def acquire(resources: List[str], lock_timeout: float, enter_timeout: float = None) -> (bool, List[str]):
    api = await _current_hub().get_distr_locks()
    if api is None:
        raise SiriusInitializationError('Configure APIDistributedLocks via "Config.override_distr_locks(...)"')
    kwargs = {'resources': resources, 'lock_timeout': lock_timeout}
    if enter_timeout:
        kwargs['enter_timeout'] = enter_timeout
    return await api.acquire(**kwargs)


async def release():
    api = await _current_hub().get_distr_locks()
    if api is None:
        raise SiriusInitializationError('Configure APIDistributedLocks via "Config.override_distr_locks(...)"')
    await api.release()
