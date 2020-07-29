import hashlib
from typing import List, Optional

from ....encryption import bytes_to_b58
from ....agent.pairwise import Pairwise
from ....agent.microledgers import serialize_ordering
from ....agent.wallet.abstract.crypto import AbstractCrypto
from ....agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage, AriesProblemReport, THREAD_DECORATOR
from ....agent.microledgers import Transaction
from ....agent.aries_rfc.utils import sign, verify_signed


class SimpleConsensusMessage(AriesProtocolMessage, metaclass=RegisterMessage):
    """Message for Simple Consensus protocol over Microledger maintenance

    """
    PROTOCOL = 'simple-consensus'

    def __init__(self, participants: List[str]=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['participants'] = participants or []

    @property
    def participants(self) -> List[str]:
        return self.get('participants', [])


class InitLedgerMessage(SimpleConsensusMessage):

    NAME = 'initialize-request'
    
    def __init__(
            self, ledger_name: Optional[str]=None, genesis: List[Transaction]=None,
            root_hash: Optional[str]=None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        ledger = {}
        if ledger_name is not None:
            ledger['name'] = ledger_name
        if root_hash is not None:
            ledger['root_hash'] = root_hash
        if genesis is not None:
            ledger['genesis'] = genesis
        if ledger:
            self['ledger'] = ledger
            hashfunc = hashlib.sha256
            hasher = hashfunc()
            data = serialize_ordering(ledger)
            hasher.update(data)
            digest = hasher.digest()
            self['ledger~hash'] = {
                'func': 'sha256',
                'base58': bytes_to_b58(digest)
            }

    @property
    def ledger(self) -> Optional[dict]:
        return self.get('ledger', None)

    @property
    def ledger_hash(self) -> Optional[dict]:
        return self.get('ledger~hash', None)

    @property
    def signatures(self) -> List[dict]:
        return self.get('signatures', [])

    async def add_signature(self, me: Pairwise.Me, api: AbstractCrypto):
        if me.did not in self.participants:
            raise RuntimeError('Signer must be a participant')
        if self.ledger_hash is not None:
            hash_signature = await sign(api, self.ledger_hash, me.verkey)
            signatures = [s for s in self.signatures if s['id'] != me.did]
            signatures.append(
                {
                    'participant': me.did,
                    'signature': hash_signature
                }
            )
            self['signatures'] = signatures
        else:
            raise RuntimeError('Ledger description is empty')
