import hashlib
from typing import List, Optional

from ....encryption import bytes_to_b58
from ....errors.exceptions import *
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


class SimpleConsensusProblemReport(AriesProblemReport, metaclass=RegisterMessage):
    PROTOCOL = SimpleConsensusMessage.PROTOCOL


class BaseInitLedgerMessage(SimpleConsensusMessage):

    NAME = 'initialize'
    
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

    async def check_signatures(self, api: AbstractCrypto, participant: str = 'ALL'):
        if self.ledger_hash is None:
            raise SiriusContextError('Ledger Hash description is empty')
        if participant == 'ALL':
            signatures = self.signatures
        else:
            signatures = [s for s in self.signatures if s['participant'] == participant]
        if signatures:
            for item in signatures:
                signed_ledger_hash, is_success = await verify_signed(api, item['signature'])
                if not is_success:
                    raise SiriusValidationError('Invalid Sign for participant: "%s"' % item['participant'])
                if signed_ledger_hash != self.ledger_hash:
                    raise SiriusValidationError('NonConsistent Ledger hash for participant: "%s"' % item['participant'])
        else:
            raise SiriusContextError('Signatures list is empty!')


class InitRequestLedgerMessage(BaseInitLedgerMessage):

    NAME = 'initialize-request'

    @property
    def thread_id(self) -> Optional[str]:
        return self.get(THREAD_DECORATOR, {}).get('thid', None)

    async def add_signature(self, api: AbstractCrypto, me: Pairwise.Me):
        if me.did not in self.participants:
            raise SiriusContextError('Signer must be a participant')
        if self.ledger_hash is not None:
            hash_signature = await sign(api, self.ledger_hash, me.verkey)
            signatures = [s for s in self.signatures if s['participant'] != me.did]
            signatures.append(
                {
                    'participant': me.did,
                    'signature': hash_signature
                }
            )
            self['signatures'] = signatures
        else:
            raise SiriusContextError('Ledger Hash description is empty')

    async def check_ledger_hash(self):
        if not self.ledger_hash:
            raise SiriusContextError('Ledger hash is empty')
        if not self.ledger:
            raise SiriusContextError('Ledger body is empty')


class InitResponseLedgerMessage(InitRequestLedgerMessage):

    NAME = 'initialize-response'

    def assign_from(self, source: BaseInitLedgerMessage):
        partial = {k: v for k, v in source.items() if k not in ['@id', '@type']}
        self.update(partial)

    def signature(self, did: str) -> Optional[dict]:
        filtered = [p for p in self.signatures if p['participant'] == did]
        return filtered[0] if filtered else None
