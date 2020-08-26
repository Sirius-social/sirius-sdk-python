import json
import hashlib
from typing import List, Optional

from sirius_sdk.encryption import bytes_to_b58
from sirius_sdk.errors.exceptions import *
from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.agent.microledgers import serialize_ordering, Microledger
from sirius_sdk.agent.wallet.abstract.crypto import AbstractCrypto
from sirius_sdk.agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage, AriesProblemReport, THREAD_DECORATOR
from sirius_sdk.agent.microledgers import Transaction
from sirius_sdk.agent.aries_rfc.utils import sign, verify_signed


class SimpleConsensusMessage(AriesProtocolMessage, metaclass=RegisterMessage):
    """Message for Simple Consensus protocol over Microledger maintenance

    """
    PROTOCOL = 'simple-consensus'

    def __init__(self, participants: List[str] = None, *args, **kwargs):
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
            self, ledger_name: Optional[str] = None, genesis: List[Transaction] = None,
            root_hash: Optional[str] = None, *args, **kwargs
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

    async def check_signatures(self, api: AbstractCrypto, participant: str = 'ALL') -> dict:
        if self.ledger_hash is None:
            raise SiriusContextError('Ledger Hash description is empty')
        if participant == 'ALL':
            signatures = self.signatures
        else:
            signatures = [s for s in self.signatures if s['participant'] == participant]
        if signatures:
            response = {}
            for item in signatures:
                signed_ledger_hash, is_success = await verify_signed(api, item['signature'])
                if not is_success:
                    raise SiriusValidationError('Invalid Sign for participant: "%s"' % item['participant'])
                if signed_ledger_hash != self.ledger_hash:
                    raise SiriusValidationError('NonConsistent Ledger hash for participant: "%s"' % item['participant'])
                response[item['participant']] = signed_ledger_hash
            return response
        else:
            raise SiriusContextError('Signatures list is empty!')


class InitRequestLedgerMessage(BaseInitLedgerMessage):

    NAME = 'initialize-request'

    def __init__(self, timeout_sec: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if timeout_sec:
            self['timeout_sec'] = timeout_sec

    @property
    def timeout_sec(self) -> Optional[int]:
        return self.get('timeout_sec', None)

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

    def validate(self):
        super().validate()
        if not self.ledger:
            raise SiriusValidationError('Ledger info is empty')
        for expect_field in ['root_hash', 'name', 'genesis']:
            if expect_field not in self.ledger.keys():
                raise SiriusValidationError(f'Expected field "{expect_field}" does not exists in Ledger container')
        if not self.ledger_hash:
            raise SiriusValidationError('Ledger Hash info is empty')
        for expect_field in ['func', 'base58']:
            if expect_field not in self.ledger_hash.keys():
                raise SiriusValidationError(f'Expected field "{expect_field}" does not exists in Ledger Hash')


class InitResponseLedgerMessage(InitRequestLedgerMessage):

    NAME = 'initialize-response'

    def assign_from(self, source: BaseInitLedgerMessage):
        partial = {k: v for k, v in source.items() if k not in ['@id', '@type', THREAD_DECORATOR]}
        self.update(partial)

    def signature(self, did: str) -> Optional[dict]:
        filtered = [p for p in self.signatures if p['participant'] == did]
        return filtered[0] if filtered else None


class MicroLedgerState(dict):

    @classmethod
    def from_ledger(cls, ledger: Microledger):
        return MicroLedgerState(
            {
                'name': ledger.name,
                'seq_no': ledger.seq_no,
                'size': ledger.size,
                'uncommitted_size': ledger.uncommitted_size,
                'root_hash': ledger.root_hash,
                'uncommitted_root_hash': ledger.uncommitted_root_hash
            }
        )

    def is_filled(self) -> bool:
        return all(
            [
                k in self.keys() for k in
                ('name', 'seq_no', 'size', 'uncommitted_size', 'root_hash', 'uncommitted_root_hash')
            ]
        )

    @property
    def name(self) -> str:
        return self['name']

    @name.setter
    def name(self, value: int):
        self['name'] = value

    @property
    def seq_no(self) -> int:
        return self['seq_no']

    @seq_no.setter
    def seq_no(self, value: int):
        self['seq_no'] = value

    @property
    def size(self) -> int:
        return self['size']

    @size.setter
    def size(self, value: int):
        self['size'] = value

    @property
    def uncommitted_size(self) -> int:
        return self['uncommitted_size']

    @uncommitted_size.setter
    def uncommitted_size(self, value: int):
        self['uncommitted_size'] = value

    @property
    def root_hash(self) -> str:
        return self['root_hash']

    @root_hash.setter
    def root_hash(self, value: str):
        self['root_hash'] = value

    @property
    def uncommitted_root_hash(self) -> str:
        return self['uncommitted_root_hash']

    @uncommitted_root_hash.setter
    def uncommitted_root_hash(self, value: str):
        self['uncommitted_root_hash'] = value

    @property
    def hash(self) -> str:
        dump = json.dumps(self, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        return hashlib.md5(dump.encode()).hexdigest()


class BaseTransactionsMessage(SimpleConsensusMessage):

    NAME = 'stage'

    def __init__(self, transactions: List[Transaction] = None, state: Optional[MicroLedgerState] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if transactions is not None:
            for txn in transactions:
                txn = Transaction(txn)
                if not txn.has_metadata():
                    raise SiriusContextError('Transaction must have processed by Ledger engine and has metadata')
            self['transactions'] = transactions
        if state:
            state = MicroLedgerState(state)
            self['state'] = state
            self['hash'] = state.hash

    @property
    def thread_id(self) -> Optional[str]:
        return self.get(THREAD_DECORATOR, {}).get('thid', None)

    @property
    def transactions(self) -> Optional[List[Transaction]]:
        txns = self.get('transactions', None)
        if txns is not None:
            return [Transaction(txn) for txn in txns]
        else:
            return None

    @property
    def state(self) -> Optional[MicroLedgerState]:
        state = self.get('state', None)
        if state is not None:
            state = MicroLedgerState(state)
            return state if state.is_filled() else None
        else:
            return None

    @property
    def hash(self) -> Optional[str]:
        return self.get('hash', None)


class ProposeTransactionsMessage(BaseTransactionsMessage):
    """Message to process transactions propose by Actor
    """
    NAME = 'stage-propose'

    def __init__(self, timeout_sec: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if timeout_sec:
            self['timeout_sec'] = timeout_sec

    @property
    def timeout_sec(self) -> Optional[int]:
        return self.get('timeout_sec', None)

    def validate(self):
        super().validate()
        if not self.transactions:
            raise SiriusValidationError('Empty transactions list')
        for txn in self.transactions:
            if not txn.has_metadata():
                raise SiriusValidationError('Transaction has not metadata')
        if not self.state:
            raise SiriusValidationError('Empty state')
        if not self.hash:
            raise SiriusValidationError('Empty hash')


class PreCommitTransactionsMessage(BaseTransactionsMessage):
    """Message to accumulate participants signed accepts for transactions list
    """
    NAME = 'stage-pre-commit'

    async def sign_state(self, api: AbstractCrypto, me: Pairwise.Me):
        signed = await sign(api, self.hash, me.verkey)
        self['hash~sig'] = signed
        del self['state']

    async def verify_state(self, api: AbstractCrypto, expected_verkey: str) -> (bool, Optional[str]):
        hash_signed = self.get('hash~sig', None)
        if hash_signed:
            if hash_signed['signer'] == expected_verkey:
                state_hash, is_success = await verify_signed(api, hash_signed)
                return is_success, state_hash
            else:
                return False, None
        else:
            return False, None


class CommitTransactionsMessage(BaseTransactionsMessage):
    """Message to commit transactions list
    """
    NAME = 'stage-commit'

    @property
    def pre_commits(self) -> dict:
        return self.get('pre_commits', {})

    def add_pre_commit(self, participant: str, pre_commit: PreCommitTransactionsMessage):
        if 'hash~sig' not in pre_commit:
            raise SiriusContextError(f'Pre-Commit for participant {participant} does not have hash~sig attribute')
        pre_commits = self.pre_commits
        pre_commits[participant] = pre_commit['hash~sig']
        self['pre_commits'] = pre_commits

    def validate(self):
        super().validate()
        for participant in self.participants:
            if participant not in self.pre_commits.keys():
                raise SiriusValidationError(f'Pre-Commit for participant "{participant}" does not exists')

    async def verify_pre_commits(self, api: AbstractCrypto, expected_state: MicroLedgerState):
        states = {}
        for participant, signed in self.pre_commits.items():
            state_hash, is_success = await verify_signed(api, signed)
            if not is_success:
                raise SiriusValidationError(f'Error verifying pre_commit for participant: {participant}')
            if state_hash != expected_state.hash:
                raise SiriusValidationError(f'Ledger state for participant {participant} is not consistent')
            states[participant] = (expected_state, signed)
        return states


class PostCommitTransactionsMessage(BaseTransactionsMessage):
    """Message to commit transactions list
    """
    NAME = 'stage-post-commit'

    @property
    def commits(self) -> List[dict]:
        payload = self.get('commits', [])
        if payload:
            return payload
        else:
            return []

    async def add_commit_sign(self, api: AbstractCrypto, commit: CommitTransactionsMessage, me: Pairwise.Me):
        signed = await sign(api, commit, me.verkey)
        commits = self.commits
        commits.append(signed)
        self['commits'] = commits

    async def verify_commits(self, api: AbstractCrypto, expected: CommitTransactionsMessage, verkeys: List[str]) -> bool:
        actual_verkeys = [commit['signer'] for commit in self.commits]
        if not set(verkeys).issubset(set(actual_verkeys)):
            return False
        for signed in self.commits:
            commit, is_success = await verify_signed(api, signed)
            if is_success:
                cleaned_commit = {k: v for k, v in commit.items() if not k.startswith('~')}
                cleaned_expect = {k: v for k, v in expected.items() if not k.startswith('~')}
                if cleaned_commit != cleaned_expect:
                    return False
            else:
                return False
        return True

    def validate(self):
        super().validate()
        if not self.commits:
            raise SiriusValidationError('Commits collection is empty')
