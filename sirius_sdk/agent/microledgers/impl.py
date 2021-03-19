import json
from typing import Union, List, Dict

from sirius_sdk.agent.connections import AgentRPC
from sirius_sdk.agent.microledgers.abstract import AbstractMicroledgerList, Transaction, AbstractMicroledger, \
    LedgerMeta, MerkleInfo, AuditProof, AbstractBatchedAPI
from sirius_sdk.errors.exceptions import SiriusContextError
from sirius_sdk.agent.microledgers.expiringdict import ExpiringDict


class BatchedAPI(AbstractBatchedAPI):

    def __init__(self, api: AgentRPC, external: Dict[str, AbstractMicroledger] = None):
        self.__api = api
        self.__names = []
        self.__external = external

    async def open(self, ledgers: Union[List[str], List[AbstractMicroledger]]) -> List[AbstractMicroledger]:
        names_to_open = []
        for ledger in ledgers:
            if isinstance(ledger, AbstractMicroledger):
                names_to_open.append(ledger.name)
            elif isinstance(ledger, str):
                names_to_open.append(ledger)
            else:
                raise RuntimeError(f'Unexpected ledgers item type: {str(type(ledger))}')

        names_to_open = list(set(names_to_open))  # remove duplicates
        await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers-batched/1.0/open',
            params={
                'names': names_to_open
            }
        )
        self.__names = names_to_open
        states = await self.states()
        return states

    async def close(self):
        await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers-batched/1.0/close'
        )

    async def states(self) -> List[AbstractMicroledger]:
        states = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers-batched/1.0/states'
        )
        resp = self.__return_ledgers(states)
        return resp

    async def append(
            self, transactions: Union[List[Transaction], List[dict]], txn_time: Union[str, int] = None
    ) -> List[AbstractMicroledger]:
        states = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers-batched/1.0/append_txns',
            params={
                'txns': transactions,
                'txn_time': txn_time
            }
        )
        resp = self.__return_ledgers(states)
        return resp

    async def commit(self) -> List[AbstractMicroledger]:
        states = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers-batched/1.0/commit_txns'
        )
        resp = self.__return_ledgers(states)
        return resp

    async def reset_uncommitted(self) -> List[AbstractMicroledger]:
        states = await self.__api.remote_call(
            msg_type='did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/microledgers-batched/1.0/reset_uncommitted'
        )
        resp = self.__return_ledgers(states)
        return resp

    def __return_ledgers(self, states: dict) -> List[AbstractMicroledger]:
        resp = []  # keep ledgers ordering
        for name in self.__names:
            state = states[name]
            ledger = Microledger(name, self.__api, state)
            if self.__external is not None:
                if name in self.__external:
                    ledger.assign_to(self.__external[name])
                else:
                    self.__external[name] = ledger
            resp.append(ledger)
        return resp


class MicroledgerList(AbstractMicroledgerList):

    TTL = 60*60  # 1 hour

    def __init__(self, api: AgentRPC):
        self.__api = api
        self.instances: Dict[str, AbstractMicroledger] = ExpiringDict(ttl=self.TTL)
        self.__batched_api = BatchedAPI(api, self.instances)

    async def batched(self) -> AbstractBatchedAPI:
        return self.__batched_api

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


class Microledger(AbstractMicroledger):

    def __init__(self, name: str, api: AgentRPC, state: dict = None):
        self.__name = name
        self.__api = api
        self.__state = state

    def assign_to(self, other: AbstractMicroledger):
        if isinstance(other, Microledger):
            other.__state = self.__state

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