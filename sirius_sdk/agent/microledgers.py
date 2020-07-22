from typing import List, Union, Dict

from .connections import AgentRPC
from ..errors.exceptions import *


METADATA_ATTR = 'txnMetadata'


class Transaction(dict):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if METADATA_ATTR not in self:
            self[METADATA_ATTR] = {}

    @staticmethod
    def create(*args, **kwargs):
        inst = Transaction(*args, **kwargs)
        if inst[METADATA_ATTR] != {}:
            raise SiriusContextError('"%s" attribute must be empty for new transaction' % METADATA_ATTR)

    @staticmethod
    def from_value(from_: Union[List[dict], dict]) -> Union[List[Dict], Dict]:
        if isinstance(from_, list):
            return [Transaction(txn) for txn in from_]
        elif isinstance(from_, dict):
            return Transaction(from_)
        else:
            raise SiriusContextError('Unexpected input value')


class MerkleInfo:

    def __init__(self, root_hash: str, audit_path: List[str]):
        self.__root_hash = root_hash
        self.__audit_path = audit_path

    @property
    def root_hash(self) -> str:
        return self.__root_hash

    @property
    def audit_path(self) -> List[str]:
        return self.__audit_path


class AuditProof(MerkleInfo):

    def __init__(self, root_hash: str, audit_path: List[str], ledger_size: int):
        super().__init__(root_hash, audit_path)
        self.__ledger_size = ledger_size

    @property
    def ledger_size(self) -> int:
        return self.__ledger_size


class Microledger:

    def __init__(self, name: str, api: AgentRPC):
        self.__name = name
        self.__api = api
        self.__state = None

    @property
    def name(self) -> str:
        return self.__name

    @property
    def size(self) -> int:
        self.__check_state_is_exists()
        return self.__state['size']

    @property
    def uncommitted_size(self) -> int:
        self.__check_state_is_exists()
        return self.__state['uncommitted_size']

    @property
    def root_hash(self) -> str:
        self.__check_state_is_exists()
        return self.__state['root_hash']

    @property
    def uncommitted_root_hash(self) -> str:
        self.__check_state_is_exists()
        return self.__state['uncommitted_root_hash']

    @property
    def seq_no(self) -> int:
        self.__check_state_is_exists()
        return self.__state['seqNo']

    async def reload(self):
        state = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/state',
            params={
                'name': self.name
            }
        )
        self.__state = state

    async def init(self, genesis: List[Transaction]):
        await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/initialize',
            params={
                'name': self.name,
                'genesis_txns': genesis
            }
        )

    async def append(
            self, transactions: List[Transaction], txn_time: Union[str, int]=None
    ) -> (int, int, List[Transaction]):
        transactions_with_meta = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/append_txns_metadata',
            params={
                'name': self.name,
                'txns': transactions,
                'txn_time': txn_time
            }
        )
        self.__state, start, end, appended_txns = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/append_txns',
            params={
                'name': self.name,
                'txns': transactions_with_meta,
            }
        )
        return start, end, Transaction.from_value(appended_txns)

    async def commit(self, count: int) -> (int, int, List[Transaction]):
        self.__state, start, end, committed_txns = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/commit_txns',
            params={
                'name': self.name,
                'count': count,
            }
        )
        return start, end, Transaction.from_value(committed_txns)

    async def discard(self, count: int):
        self.__state = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/discard_txns',
            params={
                'name': self.name,
                'count': count,
            }
        )

    async def merkle_info(self, seq_no: int) -> MerkleInfo:
        merkle_info = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/merkle_info',
            params={
                'name': self.name,
                'seqNo': seq_no,
            }
        )
        return MerkleInfo(
            root_hash=merkle_info['rootHash'],
            audit_path=merkle_info['auditPath'],
        )

    async def audit_proof(self, seq_no: int) -> AuditProof:
        proof = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/audit_proof',
            params={
                'name': self.name,
                'seqNo': seq_no,
            }
        )
        return AuditProof(
            root_hash=proof['rootHash'],
            audit_path=proof['auditPath'],
            ledger_size=proof['ledgerSize']
        )

    async def reset_uncommitted(self):
        self.__state = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/reset_uncommitted',
            params={
                'name': self.name,
            }
        )

    async def get_transaction(self, seq_no: int) -> Transaction:
        txn = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/get_by_seq_no',
            params={
                'name': self.name,
                'seqNo': seq_no
            }
        )
        txn = Transaction.from_value(txn)
        assert isinstance(txn, Transaction)
        return txn

    async def get_uncommitted_transaction(self, seq_no: int) -> Transaction:
        txn = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/get_by_seq_no_uncommitted',
            params={
                'name': self.name,
                'seqNo': seq_no
            }
        )
        txn = Transaction.from_value(txn)
        assert isinstance(txn, Transaction)
        return txn

    async def get_last_transaction(self) -> Transaction:
        txn = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/get_last_txn',
            params={
                'name': self.name
            }
        )
        txn = Transaction.from_value(txn)
        assert isinstance(txn, Transaction)
        return txn

    async def get_last_committed_transaction(self) -> Transaction:
        txn = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/get_last_committed_txn',
            params={
                'name': self.name
            }
        )
        txn = Transaction.from_value(txn)
        assert isinstance(txn, Transaction)
        return txn

    async def get_all_transactions(self) -> List[Transaction]:
        txns = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/get_all_txns',
            params={
                'name': self.name
            }
        )
        txns = Transaction.from_value(txns)
        assert isinstance(txns, list)
        return txns

    async def get_uncommitted_transactions(self) -> List[Transaction]:
        txns = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/get_uncommitted_txns',
            params={
                'name': self.name
            }
        )
        txns = Transaction.from_value(txns)
        assert isinstance(txns, list)
        return txns

    async def reset(self):
        await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/reset',
            params={
                'name': self.name
            }
        )

    def __check_state_is_exists(self):
        if self.__state is None:
            raise SiriusContextError('Load state of Microledger at First!')



