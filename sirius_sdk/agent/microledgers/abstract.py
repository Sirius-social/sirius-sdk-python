import json
from abc import ABC, abstractmethod
from typing import List, Union, Dict, Optional

# from sirius_sdk import acquire as resources_acquire, release as resources_release
from sirius_sdk.errors.exceptions import *

METADATA_ATTR = 'txnMetadata'
ATTR_TIME = 'txnTime'


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

    @property
    def time(self) -> Optional[str]:
        return self.get(METADATA_ATTR, {}).get(ATTR_TIME)

    @time.setter
    def time(self, value: str):
        metadata = self.get(METADATA_ATTR, {})
        metadata[ATTR_TIME] = value
        self[METADATA_ATTR] = metadata

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


class AbstractBatchedAPI(ABC):

    @abstractmethod
    async def open(self, ledgers: Union[List[str], List[AbstractMicroledger]]) -> List[AbstractMicroledger]:
        pass

    @abstractmethod
    async def close(self):
        pass

    @abstractmethod
    async def states(self) -> List[AbstractMicroledger]:
        pass

    @abstractmethod
    async def append(
            self, transactions: Union[List[Transaction], List[dict]], txn_time: Union[str, int] = None
    ) -> List[AbstractMicroledger]:
        pass

    @abstractmethod
    async def commit(self) -> List[AbstractMicroledger]:
        pass

    @abstractmethod
    async def reset_uncommitted(self) -> List[AbstractMicroledger]:
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

    async def batched(self) -> Optional[AbstractBatchedAPI]:
        return None
