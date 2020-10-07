import json
from abc import ABC, abstractmethod
from typing import List, Union, Dict

from sirius_sdk.errors.exceptions import *
from sirius_sdk.agent.connections import AgentRPC


METADATA_ATTR = 'txnMetadata'


def serialize_ordering(value: dict) -> bytes:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return data


class Transaction(dict):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if METADATA_ATTR not in self:
            self[METADATA_ATTR] = {}

    def has_metadata(self) -> bool:
        if METADATA_ATTR in self.keys():
            meta = self[METADATA_ATTR]
            return len(meta.keys()) > 0
        else:
            return False

    @staticmethod
    def create(*args, **kwargs):
        inst = Transaction(*args, **kwargs)
        if inst[METADATA_ATTR] != {}:
            raise SiriusContextError('"%s" attribute must be empty for new transaction' % METADATA_ATTR)
        return inst

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


class LedgerMeta(dict):

    def __init__(self, name: str, uid: str, created: str):
        super().__init__()
        self['name'] = name
        self['uid'] = uid
        self['created'] = created

    @property
    def name(self) -> str:
        return self['name']

    @property
    def uid(self) -> str:
        return self['uid']

    @property
    def created(self) -> str:
        return self['created']


class AuditProof(MerkleInfo):

    def __init__(self, root_hash: str, audit_path: List[str], ledger_size: int):
        super().__init__(root_hash, audit_path)
        self.__ledger_size = ledger_size

    @property
    def ledger_size(self) -> int:
        return self.__ledger_size


class AbstractMicroledger(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def size(self) -> int:
        pass

    @property
    @abstractmethod
    def uncommitted_size(self) -> int:
        pass

    @property
    @abstractmethod
    def root_hash(self) -> str:
        pass

    @property
    @abstractmethod
    def uncommitted_root_hash(self) -> str:
        pass

    @property
    @abstractmethod
    def seq_no(self) -> int:
        pass

    @abstractmethod
    async def reload(self):
        pass

    @abstractmethod
    async def rename(self, new_name: str):
        pass

    @abstractmethod
    async def init(self, genesis: List[Transaction]) -> List[Transaction]:
        pass

    @abstractmethod
    async def append(
            self, transactions: Union[List[Transaction], List[dict]], txn_time: Union[str, int] = None
    ) -> (int, int, List[Transaction]):
        pass

    @abstractmethod
    async def commit(self, count: int) -> (int, int, List[Transaction]):
        pass

    @abstractmethod
    async def discard(self, count: int):
        pass

    @abstractmethod
    async def merkle_info(self, seq_no: int) -> MerkleInfo:
        pass

    @abstractmethod
    async def audit_proof(self, seq_no: int) -> AuditProof:
        pass

    @abstractmethod
    async def reset_uncommitted(self):
        pass

    @abstractmethod
    async def get_transaction(self, seq_no: int) -> Transaction:
        pass

    @abstractmethod
    async def get_uncommitted_transaction(self, seq_no: int) -> Transaction:
        pass

    @abstractmethod
    async def get_last_transaction(self) -> Transaction:
        pass

    @abstractmethod
    async def get_last_committed_transaction(self) -> Transaction:
        pass

    @abstractmethod
    async def get_all_transactions(self) -> List[Transaction]:
        pass

    @abstractmethod
    async def get_uncommitted_transactions(self) -> List[Transaction]:
        pass


class AbstractMicroledgerList(ABC):

    @abstractmethod
    async def create(self, name: str, genesis: Union[List[Transaction], List[dict]]) -> (AbstractMicroledger, List[Transaction]):
        pass

    @abstractmethod
    async def ledger(self, name: str) -> AbstractMicroledger:
        pass

    @abstractmethod
    async def reset(self, name: str):
        pass

    @abstractmethod
    async def is_exists(self, name: str):
        pass

    @abstractmethod
    async def leaf_hash(self, txn: Union[Transaction, bytes]) -> bytes:
        pass

    @abstractmethod
    async def list(self) -> List[LedgerMeta]:
        pass


class Microledger(AbstractMicroledger):

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

    async def rename(self, new_name: str):
        await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/rename',
            params={
                'name': self.name,
                'new_name': new_name
            }
        )
        self.__name = new_name

    async def init(self, genesis: List[Transaction]) -> List[Transaction]:
        self.__state, txns = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/initialize',
            params={
                'name': self.name,
                'genesis_txns': genesis
            }
        )
        txns = [Transaction.from_value(txn) for txn in txns]
        return txns

    async def append(
            self, transactions: Union[List[Transaction], List[dict]], txn_time: Union[str, int] = None
    ) -> (int, int, List[Transaction]):
        transactions_to_append = []
        for txn in transactions:
            if isinstance(txn, Transaction):
                transactions_to_append.append(txn)
            elif isinstance(txn, dict):
                transactions_to_append.append(Transaction.create(txn))
            else:
                raise RuntimeError('Unexpected transaction type')
        transactions_with_meta = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/append_txns_metadata',
            params={
                'name': self.name,
                'txns': transactions_to_append,
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
        txns = [t[1] for t in txns]
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

    def __check_state_is_exists(self):
        if self.__state is None:
            raise SiriusContextError('Load state of Microledger at First!')


class MicroledgerList(AbstractMicroledgerList):

    def __init__(self, api: AgentRPC):
        self.__api = api
        self.instances = {}

    async def create(self, name: str, genesis: Union[List[Transaction], List[dict]]) -> (AbstractMicroledger, List[Transaction]):
        genesis_txns = []
        for txn in genesis:
            if isinstance(txn, Transaction):
                genesis_txns.append(txn)
            elif isinstance(txn, dict):
                genesis_txns.append(Transaction.create(txn))
            else:
                raise RuntimeError('Unexpected transaction type')
        instance = Microledger(name, self.__api)
        txns = await instance.init(genesis_txns)
        self.instances[name] = instance
        return instance, txns

    async def ledger(self, name: str) -> AbstractMicroledger:
        if name not in self.instances:
            await self.__check_is_exists(name)
            instance = Microledger(name, self.__api)
            self.instances[name] = instance
        return self.instances[name]

    async def reset(self, name: str):
        await self.__check_is_exists(name)
        await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/reset',
            params={
                'name': name
            }
        )
        if name in self.instances.keys():
            del self.instances[name]

    async def is_exists(self, name: str):
        is_exists = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/is_exists',
            params={
                'name': name
            }
        )
        return is_exists

    async def leaf_hash(self, txn: Union[Transaction, bytes]) -> bytes:
        if isinstance(txn, Transaction):
            data = json.dumps(txn, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        elif isinstance(txn, bytes):
            data = txn
        else:
            raise RuntimeError('Unexpected transaction type')
        leaf_hash = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/leaf_hash',
            params={
                'data': data
            }
        )
        return leaf_hash

    async def list(self) -> List[LedgerMeta]:
        collection = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers/1.0/list',
            params={
                'name': '*'
            }
        )
        return [LedgerMeta(**item) for item in collection]

    async def __check_is_exists(self, name: str):
        if name not in self.instances.keys():
            is_exists = await self.is_exists(name)
            if not is_exists:
                raise SiriusContextError('MicroLedger with name "" does not exists' % name)
