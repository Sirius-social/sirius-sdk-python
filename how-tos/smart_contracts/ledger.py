import json
import hashlib
import datetime
from typing import List, Union, Optional

import sirius_sdk
from sirius_sdk.agent.microledgers import AbstractMicroledgerList, AbstractMicroledger, Transaction, AuditProof, \
    MerkleInfo, LedgerMeta


def calc_hash(seq: List[Transaction]) -> str:
    json_kwargs = {
        'ensure_ascii': False,
        'sort_keys': True,
        'separators': (',', ':')
    }
    h = hashlib.sha3_512()
    for txn in seq:
        bytes_ = json.dumps(txn, **json_kwargs).encode('utf-8')
        h.update(bytes_)
    return h.hexdigest()


class InMemoryLedger(AbstractMicroledger):

    def __init__(self, name: str):
        self.__name = name
        self.__committed = []
        self.__uncommitted = []

    @property
    def name(self) -> str:
        return self.__name

    @property
    def size(self) -> int:
        return len(self.__committed)

    @property
    def uncommitted_size(self) -> int:
        return len(self.__uncommitted)

    @property
    def root_hash(self) -> str:
        return calc_hash(self.__committed)

    @property
    def uncommitted_root_hash(self) -> str:
        return calc_hash(self.__committed + self.__uncommitted)

    @property
    def seq_no(self) -> int:
        return len(self.__committed) - 1

    async def reload(self):
        pass

    async def rename(self, new_name: str):
        raise NotImplemented

    async def init(self, genesis: List[Transaction]) -> List[Transaction]:
        if self.__committed:
            raise RuntimeError('Unexpected operation')
        for seq_no, txn in enumerate(genesis):
            metadata = txn.get('txnMetadata', {})
            if 'seq_no' not in metadata:
                metadata['seq_no'] = seq_no
            if 'time' not in metadata:
                metadata['time'] = str(datetime.datetime.utcnow())
            txn['txnMetadata'] = metadata
            self.__committed.append(txn)
        return self.__committed

    async def append(
            self, transactions: Union[List[Transaction], List[dict]], txn_time: Union[str, int] = None
    ) -> (int, int, List[Transaction]):
        txns = []
        for i, txn in enumerate(Transaction.from_value(transactions)):
            metadata = txn.get('txnMetadata', {})
            if 'seq_no' not in metadata:
                metadata['seq_no'] = self.seq_no + 1 + i
            if 'time' not in metadata:
                metadata['time'] = txn_time or str(datetime.datetime.utcnow())
            txn['txnMetadata'] = metadata
            txns.append(txn)
        start = self.seq_no + 1
        end = start + len(txns) - 1
        self.__uncommitted.extend(txns)
        return start, end, txns

    async def commit(self, count: int) -> (int, int, List[Transaction]):
        start = self.seq_no + 1
        txns = self.__uncommitted[:count]
        self.__committed.extend(txns)
        self.__uncommitted = self.__uncommitted[count:]
        stop = self.seq_no
        return start, stop, txns

    async def discard(self, count: int):
        self.__uncommitted.clear()

    async def merkle_info(self, seq_no: int) -> MerkleInfo:
        raise NotImplemented

    async def audit_proof(self, seq_no: int) -> AuditProof:
        raise NotImplemented

    async def reset_uncommitted(self):
        self.__uncommitted.clear()

    async def get_transaction(self, seq_no: int) -> Transaction:
        if seq_no <= self.seq_no:
            return self.__committed[seq_no]
        else:
            return await self.get_uncommitted_transaction(seq_no)

    async def get_uncommitted_transaction(self, seq_no: int) -> Transaction:
        return self.__uncommitted[seq_no - len(self.__committed)]

    async def get_last_transaction(self) -> Transaction:
        if self.__uncommitted:
            return self.__uncommitted[-1]
        else:
            return self.__committed[-1]

    async def get_last_committed_transaction(self) -> Transaction:
        return self.__committed[-1]

    async def get_all_transactions(self) -> List[Transaction]:
        return self.__committed + self.__uncommitted

    async def get_uncommitted_transactions(self) -> List[Transaction]:
        return self.__uncommitted[-1]


class InMemoryLedgerList(AbstractMicroledgerList):

    def __init__(self):
        self.__ledgers = {}

    async def create(
            self, name: str, genesis: Union[List[Transaction], List[dict]]
    ) -> (AbstractMicroledger, List[Transaction]):
        if name in self.__ledgers.keys():
            raise RuntimeError('Already exists')
        ledger = InMemoryLedger(name)
        txns = await ledger.init(genesis)
        return ledger, txns

    async def ledger(self, name: str) -> AbstractMicroledger:
        ledger = self.__ledgers.get(name, None)
        if ledger:
            return ledger
        else:
            raise RuntimeError('Not exists')

    async def reset(self, name: str):
        if name in self.__ledgers:
            del self.__ledgers[name]

    async def is_exists(self, name: str):
        return name in self.__ledgers.keys()

    async def leaf_hash(self, txn: Union[Transaction, bytes]) -> bytes:
        raise NotImplemented

    async def list(self) -> List[LedgerMeta]:
        raise NotImplemented
