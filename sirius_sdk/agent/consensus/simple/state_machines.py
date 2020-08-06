import uuid
import logging
from datetime import datetime
from typing import List, Union

from ....agent.pairwise import Pairwise
from ....agent.wallet.abstract.crypto import AbstractCrypto
from ....agent.pairwise import AbstractPairwiseList
from ....agent.microledgers import Transaction, Microledger, MicroledgerList
from ....agent.sm import AbstractStateMachine
from ....agent.aries_rfc.feature_0015_acks import Ack, Status
from .messages import *

# Problem codes
REQUEST_NOT_ACCEPTED = "request_not_accepted"
REQUEST_PROCESSING_ERROR = 'request_processing_error'
RESPONSE_NOT_ACCEPTED = "response_not_accepted"
RESPONSE_PROCESSING_ERROR = 'response_processing_error'


class MicroLedgerSimpleConsensus(AbstractStateMachine):

    def __init__(
            self, crypto: AbstractCrypto, me: Pairwise.Me,
            pairwise_list: AbstractPairwiseList, microledgers: MicroledgerList, *args, **kwargs
    ):
        self.__me = me
        self.__problem_report = None
        self.__microledgers = microledgers
        self.__crypto = crypto
        self.__pairwise_list = pairwise_list
        self.__transport = None
        self.__thread_id = None
        self.__cached_p2p = {}
        super().__init__(*args, **kwargs)

    @property
    def me(self) -> Pairwise.Me:
        return self.__me

    @property
    def crypto(self) -> AbstractCrypto:
        return self.__crypto

    @property
    def microledgers(self) -> MicroledgerList:
        return self.__microledgers

    @property
    def pairwise_list(self) -> AbstractPairwiseList:
        return self.__pairwise_list

    @property
    def protocols(self) -> List[str]:
        return [SimpleConsensusMessage.PROTOCOL, Ack.PROTOCOL]

    @property
    def problem_report(self) -> SimpleConsensusProblemReport:
        return self.__problem_report

    async def init_microledger(
            self, ledger_name: str, participants: List[str], genesis: List[Transaction]
    ) -> (bool, Microledger):
        participants = list(set(participants + [self.me.did]))
        await self._setup('simple-consensus-' + uuid.uuid4().hex, self.time_to_live)
        try:
            ledger, genesis = await self.microledgers.create(ledger_name, genesis)
            try:
                await self._init_microledger_internal(ledger, participants, genesis)
            except Exception as e:
                await self.microledgers.reset(ledger_name)
                if isinstance(e, SimpleConsensusProblemReport):
                    return False, None
                else:
                    raise
            else:
                return True, ledger
        finally:
            await self._clean()

    async def accept_microledger(self, actor: Pairwise, propose: InitRequestLedgerMessage) -> (bool, Microledger):
        if self.me.did not in propose.participants:
            raise SiriusContextError('Invalid state machine initialization')
        time_to_live = propose.timeout_sec or self.time_to_live
        await self._setup(propose.thread_id, time_to_live)
        try:
            ledger_name = propose.ledger.get('name', None)
            if not ledger_name:
                await self._terminate_with_problem_report(
                    problem_code=REQUEST_PROCESSING_ERROR,
                    explain='Ledger name is Empty!',
                    their_did=actor.their.did,
                )
            try:
                for their_did in propose.participants:
                    if their_did != self.me.did:
                        pw = await self.get_p2p(their_did, raise_exception=False)
                        if pw is None:
                            await self._terminate_with_problem_report(
                                problem_code=REQUEST_PROCESSING_ERROR,
                                explain=f'Pairwise for DID: "their_did" does not exists!' % their_did,
                                their_did=actor.their.did
                            )
                ledger = await self._accept_microledger_internal(actor, propose, time_to_live)
            except Exception as e:
                await self.microledgers.reset(ledger_name)
                if isinstance(e, SimpleConsensusProblemReport):
                    return False, None
                else:
                    raise
            else:
                return True, ledger
        finally:
            await self._clean()

    async def commit(
            self, ledger: Microledger, participants: List[str], transactions: List[Transaction]
    ) -> (bool, Optional[List[Transaction]]):
        await self._setup('simple-consensus-txns-' + uuid.uuid4().hex, self.time_to_live)
        try:
            try:
                txns = await self._commit_internal(ledger, transactions, participants)
                return True, txns
            except Exception as e:
                await ledger.reset_uncommitted()
                if isinstance(e, SimpleConsensusProblemReport):
                    return False, None
                else:
                    raise
        finally:
            await self._clean()

    async def accept_commit(self, actor: Pairwise, propose: ProposeTransactionsMessage) -> bool:
        time_to_live = propose.timeout_sec or self.time_to_live
        await self._setup(propose.thread_id, time_to_live)
        try:
            ledger = None
            try:
                ledger = await self._load_ledger(actor, propose)
                await self._accept_commit_internal(ledger, actor, propose)
                return True
            except Exception as e:
                if ledger:
                    await ledger.reset_uncommitted()
                if isinstance(e, SimpleConsensusProblemReport):
                    return False
                else:
                    raise
        finally:
            await self._clean()

    async def _switch(
            self, their_did: str, req: Union[SimpleConsensusMessage, SimpleConsensusProblemReport, Ack]
    ) -> (bool, Union[SimpleConsensusMessage, SimpleConsensusProblemReport]):
        if isinstance(req, SimpleConsensusMessage) or isinstance(req, SimpleConsensusProblemReport) or isinstance(req, Ack):
            pw = await self.get_p2p(their_did)
            self.__transport.pairwise = pw
            ok, resp = await self.__transport.switch(req)
            if isinstance(resp, SimpleConsensusMessage) or isinstance(resp, SimpleConsensusProblemReport) or isinstance(resp, Ack):
                return ok, resp
            else:
                await self._terminate_with_problem_report(
                    problem_code=RESPONSE_NOT_ACCEPTED,
                    explain=f'Unexpected message with @type = {resp.type}',
                    their_did=their_did
                )
        else:
            raise SiriusContextError('Unexpected req type')

    async def _send(self, their_did: Union[str, List[str]], message: AriesProtocolMessage):
        if isinstance(their_did, str):
            recipients = [their_did]
        elif isinstance(their_did, list):
            recipients = their_did
        else:
            raise SiriusContextError('Unexpected their_did type')
        for did in recipients:
            pw = await self.get_p2p(did)
            self.__transport.pairwise = pw
            await self.__transport.send(message)

    async def _setup(self, thread_id: str, time_to_live: int):
        self.__thread_id = thread_id
        self.__transport = await self.transports.spawn(thread_id)
        await self.__transport.start(time_to_live=time_to_live)

    async def _clean(self):
        if self.__transport:
            await self.__transport.stop()
        self.__transport = None

    async def get_p2p(self, their_did: str, raise_exception: bool = True) -> Pairwise:
        if their_did not in self.__cached_p2p.keys():
            pw = await self.pairwise_list.load_for_did(their_did)
            if pw is None and raise_exception:
                raise SiriusContextError('Pairwise for "%s" does not exists!' % their_did)
            self.__cached_p2p[their_did] = pw
        return self.__cached_p2p[their_did]

    async def _terminate_with_problem_report(
            self, problem_code: str, explain, their_did: Union[str, List[str]], raise_exception: bool=True
    ):
        self.__problem_report = SimpleConsensusProblemReport(
            problem_code=problem_code, explain=explain, thread_id=self.__thread_id
        )
        if isinstance(their_did, str):
            await self._send(their_did, self.__problem_report)
        elif isinstance(their_did, list):
            for did in their_did:
                await self._send(did, self.__problem_report)
        else:
            raise SiriusContextError('Unexpected their_did type')
        if raise_exception:
            raise self.__problem_report

    async def _init_microledger_internal(
            self, ledger: Microledger, participants: List[str], genesis: List[Transaction]
    ):
        # ============= STAGE 1: PROPOSE =================
        propose = InitRequestLedgerMessage(
            timeout_sec=self.time_to_live,
            ledger_name=ledger.name,
            genesis=genesis,
            root_hash=ledger.root_hash,
            participants=[did for did in participants]
        )
        await propose.add_signature(self.crypto, self.me)
        request_commit = InitResponseLedgerMessage()
        request_commit.assign_from(propose)
        neighbours = [did for did in participants if did != self.me.did]
        for their_did in neighbours:
            ok, response = await self._switch(their_did, propose)
            if ok:
                if isinstance(response, InitResponseLedgerMessage):
                    response.validate()
                    await response.check_signatures(self.crypto, their_did)
                    signature = response.signature(their_did)
                    request_commit.signatures.append(signature)
                elif isinstance(response, SimpleConsensusProblemReport):
                    self.__problem_report = response
                    logging.error('Code: %s; Explain: %s' % (response.problem_code, response.explain))
                    raise self.__problem_report
            else:
                await self._terminate_with_problem_report(
                    problem_code=RESPONSE_PROCESSING_ERROR,
                    explain='Stage-1: Response awaiting was terminated by timeout for participant: %s' % their_did,
                    their_did=their_did
                )
        # ============= STAGE 2: COMMIT ============
        acks = []
        for their_did in neighbours:
            sub_neighbours = [did for did in neighbours if did != their_did]
            ok, response = await self._switch(their_did, request_commit)
            if ok:
                acks.append(their_did)
            else:
                self.__problem_report = SimpleConsensusProblemReport(
                    problem_code=RESPONSE_PROCESSING_ERROR,
                    explain='Stage-2: Response awaiting was terminated for participant: %s' % their_did,
                    thread_id=self.__thread_id
                )
                for did in sub_neighbours:
                    await self._send(did, self.__problem_report)
                raise self.__problem_report
        # ============== STAGE 3: POST-COMMIT ============
        if set(acks) == set(neighbours):
            for their_did in neighbours:
                ack = Ack(thread_id=self.__thread_id, status=Status.OK)
                await self._send(their_did, ack)
        else:
            acks_str = ','.join(acks)
            neighbours_str = ','.join(neighbours)
            self.__problem_report = SimpleConsensusProblemReport(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain=f'Stage-3: Actual list of acceptors: [{acks_str}]  Expected: [{neighbours_str}]',
                thread_id=self.__thread_id
            )
            for did in neighbours:
                await self._send(did, self.__problem_report)
            raise self.__problem_report

    async def _accept_microledger_internal(
            self, actor: Pairwise, propose: InitRequestLedgerMessage, timeout: int
    ) -> Microledger:
        # =============== STAGE 1: PROPOSE ===============
        try:
            propose.validate()
            await propose.check_signatures(self.crypto, actor.their.did)
            if len(propose.participants) < 2:
                raise SiriusValidationError('Stage-1: participants less than 2')
        except SiriusValidationError as e:
            await self._terminate_with_problem_report(REQUEST_NOT_ACCEPTED, e.message, actor.their.did)
        genesis = [Transaction(txn) for txn in propose.ledger['genesis']]
        ledger, txns = await self.microledgers.create(propose.ledger['name'], genesis)
        if propose.ledger['root_hash'] != ledger.root_hash:
            await self.microledgers.reset(ledger.name)
            await self._terminate_with_problem_report(
                REQUEST_PROCESSING_ERROR, 'Stage-1: Non-consistent Root Hash', actor.their.did
            )
        response = InitResponseLedgerMessage(timeout_sec=timeout)
        response.assign_from(propose)
        commit_ledger_hash = response.ledger_hash
        await response.add_signature(self.crypto, self.me)
        # =============== STAGE 2: COMMIT ===============
        ok, request_commit = await self._switch(actor.their.did, response)
        if ok:
            if isinstance(request_commit, InitResponseLedgerMessage):
                try:
                    request_commit.validate()
                    hashes = await request_commit.check_signatures(self.crypto, participant='ALL')
                    for their_did, decoded in hashes.items():
                        if decoded != commit_ledger_hash:
                            raise SiriusValidationError(f'Stage-2: NonEqual Ledger hash with participant "{their_did}"')
                except SiriusValidationError as e:
                    await self._terminate_with_problem_report(REQUEST_NOT_ACCEPTED, e.message, actor.their.did)
                commit_participants_set = set(request_commit.participants)
                propose_participants_set = set(propose.participants)
                signers_set = set([s['participant'] for s in request_commit.signatures])
                if propose_participants_set != signers_set:
                    error_explain = 'Stage-2: Set of signers differs from proposed participants set'
                elif commit_participants_set != signers_set:
                    error_explain = 'Stage-2: Set of signers differs from commit participants set'
                else:
                    error_explain = None
                if error_explain:
                    await self._terminate_with_problem_report(
                        problem_code=REQUEST_NOT_ACCEPTED,
                        explain=error_explain,
                        their_did=actor.their.did
                    )
                else:
                    # Accept commit
                    ack = Ack(thread_id=self.__thread_id, status=Status.OK)
                    ok, resp = await self._switch(actor.their.did, ack)
                    # =========== STAGE-3: POST-COMMIT ===============
                    if ok:
                        if isinstance(resp, Ack):
                            return ledger
                        elif isinstance(resp, SimpleConsensusProblemReport):
                            self.__problem_report = resp
                            logging.error(
                                'Code: %s; Explain: %s' % (resp.problem_code, resp.explain))
                            raise self.__problem_report
                    else:
                        await self._terminate_with_problem_report(
                            problem_code=REQUEST_PROCESSING_ERROR,
                            explain='Stage-3: Commit accepting was terminated by timeout for actor: %s' % actor.their.did,
                            their_did=actor.their.did
                        )
            elif isinstance(request_commit, SimpleConsensusProblemReport):
                self.__problem_report = request_commit
                raise self.__problem_report
        else:
            await self._terminate_with_problem_report(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Stage-2: Commit response awaiting was terminated by timeout for actor: %s' % actor.their.did,
                their_did=actor.their.did
            )

    async def _commit_internal(
            self, ledger: Microledger, transactions: List[Transaction], participants: List[str]
    ) -> List[Transaction]:
        participants = list(set(participants + [self.me.did]))
        neighbours = [did for did in participants if did != self.me.did]
        for their_did in neighbours:
            await self.get_p2p(their_did, raise_exception=True)
        verkeys = {}
        for their_did in neighbours:
            pw = await self.get_p2p(their_did)
            verkeys[their_did] = pw.their.verkey
        txn_time = str(datetime.utcnow())
        start, end, txns = await ledger.append(transactions, txn_time)
        propose = ProposeTransactionsMessage(
            transactions=txns,
            state=MicroLedgerState.from_ledger(ledger),
            participants=participants,
            timeout_sec=self.time_to_live
        )
        # ==== STAGE-1 Propose transactions to participants ====
        commit = CommitTransactionsMessage(participants=participants)
        self_pre_commit = PreCommitTransactionsMessage(state=propose.state)
        await self_pre_commit.sign_state(self.crypto, self.me)
        commit.add_pre_commit(
            participant=self.me.did,
            pre_commit=self_pre_commit
        )
        awaited_list = []
        for their_did in neighbours:
            ok, pre_commit = await self._switch(their_did, propose)
            if ok:
                if isinstance(pre_commit, PreCommitTransactionsMessage):
                    try:
                        pre_commit.validate()
                        success, state = await pre_commit.verify_state(self.crypto, verkeys[their_did])
                        if not success:
                            raise SiriusValidationError(
                                f'Stage-1: Error verifying signed ledger state for participant {their_did}'
                            )
                        if pre_commit.state != propose.state:
                            raise SiriusValidationError(
                                f'Stage-1: Non-consistent ledger state for participant {their_did}'
                            )
                    except SiriusValidationError as e:
                        await self._terminate_with_problem_report(
                            RESPONSE_NOT_ACCEPTED,
                            f'Stage-1: Error for participant {their_did}: "{e.message}"',
                            awaited_list
                        )
                    else:
                        commit.add_pre_commit(their_did, pre_commit)
                        awaited_list.append(their_did)
                elif isinstance(pre_commit, SimpleConsensusProblemReport):
                    explain = f'Stage-1: Problem report from participant {their_did} "{pre_commit.explain}"'
                    self.__problem_report = SimpleConsensusProblemReport(pre_commit.problem_code, explain)
                    await self._send([did for did in neighbours if did != their_did], self.__problem_report)
                    raise self.__problem_report
            else:
                await self._terminate_with_problem_report(
                    problem_code=RESPONSE_PROCESSING_ERROR,
                    explain=f'Stage-1: Pre-Commit awaiting terminated by timeout for participant: {their_did}',
                    their_did=awaited_list
                )
        # ===== STAGE-2: Accumulate pre-commits and send commit propose to all participants
        post_commit_all = PostCommitTransactionsMessage()
        await post_commit_all.add_commit_sign(self.crypto, commit, self.me)
        for their_did in neighbours:
            ok, post_commit = await self._switch(their_did, commit)
            if ok:
                if isinstance(post_commit, PostCommitTransactionsMessage):
                    try:
                        post_commit.validate()
                    except SiriusValidationError as e:
                        await self._terminate_with_problem_report(
                            RESPONSE_NOT_ACCEPTED,
                            f'Stage-2: Error for participant {their_did}: "{e.message}"',
                            neighbours
                        )
                    else:
                        post_commit_all['commits'].extend(post_commit.commits)
                elif isinstance(post_commit, SimpleConsensusProblemReport):
                    explain = f'Stage-2: Problem report from participant {their_did} "{post_commit.explain}"'
                    self.__problem_report = SimpleConsensusProblemReport(post_commit.problem_code, explain)
                    await self._send([did for did in neighbours if did != their_did], self.__problem_report)
                    raise self.__problem_report
            else:
                await self._terminate_with_problem_report(
                    problem_code=RESPONSE_PROCESSING_ERROR,
                    explain=f'Stage-2: Post-Commit awaiting terminated by timeout for participant: {their_did}',
                    their_did=neighbours
                )
        # ===== STAGE-3: Notify all participants with post-commits and finalize process
        for their_did in neighbours:
            await self._send(their_did, post_commit_all)
        uncommitted_size = ledger.uncommitted_size - ledger.size
        await ledger.commit(uncommitted_size)
        return txns

    async def _load_ledger(self, actor: Pairwise, propose: ProposeTransactionsMessage) -> Microledger:
        neighbours = [did for did in propose.participants if did != self.me.did]
        try:
            propose.validate()
            if len(propose.participants) < 2:
                raise SiriusValidationError(f'Stage-1: participant count less than 2')
            if self.me.did not in propose.participants:
                raise SiriusValidationError(f'Stage-1: {self.me.did} is not participant')
            for their_did in neighbours:
                pw = await self.get_p2p(their_did)
                if pw is None:
                    raise SiriusValidationError(f'Stage-1: Pairwise for did: {their_did} does not exists')
            is_ledger_exists = await self.microledgers.is_exists(propose.state.name)
            if not is_ledger_exists:
                raise SiriusValidationError(f'Stage-1: Ledger with name {propose.state.name} does not exists')
        except SiriusValidationError as e:
            await self._terminate_with_problem_report(
                problem_code=RESPONSE_NOT_ACCEPTED,
                explain=e.message,
                their_did=actor.their.did
            )
        ledger = await self.microledgers.ledger(propose.state.name)
        return ledger

    async def _accept_commit_internal(self, ledger: Microledger, actor: Pairwise, propose: ProposeTransactionsMessage):
        neighbours = [did for did in propose.participants if did != self.me.did]
        # ===== STAGE-1: Process Propose, apply transactions and response ledger state on self-side
        await ledger.append(propose.transactions)
        ledger_state = MicroLedgerState.from_ledger(ledger)
        pre_commit = PreCommitTransactionsMessage(state=MicroLedgerState.from_ledger(ledger))
        await pre_commit.sign_state(self.crypto, self.me)
        ok, commit = await self._switch(actor.their.did, pre_commit)
        if ok:
            if isinstance(commit, CommitTransactionsMessage):
                # ===== STAGE-2: Process Commit request, check neighbours signatures
                try:
                    if set(commit.participants) != set(propose.participants):
                        raise SiriusValidationError('Non-consistent participants')
                    commit.validate()
                    await commit.verify_pre_commits(self.crypto, ledger_state)
                except SiriusValidationError as e:
                    raise self._terminate_with_problem_report(
                        problem_code=REQUEST_NOT_ACCEPTED,
                        explain=f'Stage-2: error for actor {actor.their.did}: "{e.message}"',
                        their_did=actor.their.did
                    )
                else:
                    # ===== STAGE-3: Process post-commit, verify participants operations
                    post_commit = PostCommitTransactionsMessage()
                    await post_commit.add_commit_sign(self.crypto, commit, self.me)
                    ok, post_commit_all = await self._switch(actor.their.did, post_commit)
                    if ok:
                        if isinstance(post_commit_all, PostCommitTransactionsMessage):
                            try:
                                post_commit_all.validate()
                            except SiriusValidationError as e:
                                raise self._terminate_with_problem_report(
                                    problem_code=REQUEST_NOT_ACCEPTED,
                                    explain=f'Stage-3: error for actor {actor.their.did}: "{e.message}"',
                                    their_did=actor.their.did
                                )
                            else:
                                uncommitted_size = ledger_state.uncommitted_size - ledger_state.size
                                await ledger.commit(uncommitted_size)
                        elif isinstance(post_commit_all, SimpleConsensusProblemReport):
                            explain = f'Stage-3: Problem report from actor {actor.their.did}: "{post_commit_all.explain}"'
                            self.__problem_report = SimpleConsensusProblemReport(post_commit_all.problem_code, explain)
                            raise self.__problem_report
                    else:
                        await self._terminate_with_problem_report(
                            problem_code=REQUEST_PROCESSING_ERROR,
                            explain=f'Stage-3: Post-Commit awaiting terminated by timeout for actor: {actor.their.did}',
                            their_did=actor.their.did
                        )
            elif isinstance(pre_commit, SimpleConsensusProblemReport):
                explain = f'Stage-1: Problem report from actor {actor.their.did}: "{pre_commit.explain}"'
                self.__problem_report = SimpleConsensusProblemReport(pre_commit.problem_code, explain)
                raise self.__problem_report
        else:
            await self._terminate_with_problem_report(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain=f'Stage-1: Commit awaiting terminated by timeout for actor: {actor.their.did}',
                their_did=actor.their.did
            )
