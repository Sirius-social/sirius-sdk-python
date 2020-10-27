import uuid
import logging
import contextlib
from datetime import datetime
from typing import Union, Tuple

import sirius_sdk
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.agent.microledgers import MicroledgerList, AbstractMicroledger
from sirius_sdk.hub import CoProtocolThreadedTheirs, CoProtocolThreadedP2P
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.agent.aries_rfc.feature_0015_acks import Ack, Status
from sirius_sdk.agent.consensus.simple.messages import *

# Problem codes
REQUEST_NOT_ACCEPTED = "request_not_accepted"
REQUEST_PROCESSING_ERROR = 'request_processing_error'
RESPONSE_NOT_ACCEPTED = "response_not_accepted"
RESPONSE_PROCESSING_ERROR = 'response_processing_error'


class MicroLedgerSimpleConsensus(AbstractStateMachine):

    def __init__(self, me: Pairwise.Me, time_to_live: int = 60, logger=None, *args, **kwargs):
        super().__init__(time_to_live=time_to_live, logger=logger, *args, **kwargs)
        self.__me = me
        self.__problem_report = None
        self.__cached_p2p = {}

    @property
    def me(self) -> Pairwise.Me:
        return self.__me

    @property
    def problem_report(self) -> SimpleConsensusProblemReport:
        return self.__problem_report

    @contextlib.asynccontextmanager
    async def acceptors(self, theirs: List[Pairwise], thread_id: str):
        co = CoProtocolThreadedTheirs(
            thid=thread_id,
            theirs=theirs
        )
        self._register_for_aborting(co)
        try:
            try:
                yield co
            except OperationAbortedManually:
                await self.log(progress=100, message='Aborted')
                raise StateMachineAborted('Aborted by User')
        finally:
            self._unregister_for_aborting(co)

    @contextlib.asynccontextmanager
    async def leader(self, their: Pairwise, thread_id: str, time_to_live: int = None):
        co = CoProtocolThreadedP2P(
            thid=thread_id,
            to=their,
            time_to_live=time_to_live or self.time_to_live
        )
        self._register_for_aborting(co)
        try:
            try:
                yield co
            except OperationAbortedManually:
                await self.log(progress=100, message='Aborted')
                raise StateMachineAborted('Aborted by User')
        finally:
            self._unregister_for_aborting(co)

    async def init_microledger(
            self, ledger_name: str, participants: List[str], genesis: List[Transaction]
    ) -> (bool, Microledger):
        """
        :param ledger_name: name of new microledger
        :param participants: list of DIDs that present pairwise list of the Microledger relationships
                (Assumed DIDs are public or every participant has relationship with each other via pairwise)
        :param genesis: genesis block of the new microledger if all participants accept transaction
        """
        await self._bootstrap(participants)
        relationships = [p2p for p2p in self.__cached_p2p.values()]
        async with self.acceptors(theirs=relationships, thread_id='simple-consensus-init-' + uuid.uuid4().hex) as co:
            await self.log(progress=0, message=f'Create ledger [{ledger_name}]')
            ledger, genesis = await sirius_sdk.Microledgers.create(ledger_name, genesis)
            await self.log(message=f'Ledger creation terminated successfully')
            try:
                await self._init_microledger_internal(co, ledger, participants, genesis)
                await self.log(progress=100, message='All participants accepted ledger creation')
            except Exception as e:
                await sirius_sdk.Microledgers.reset(ledger_name)
                await self.log(message=f'Reset ledger')
                if isinstance(e, StateMachineTerminatedWithError):
                    self.__problem_report = SimpleConsensusProblemReport(e.problem_code, e.explain)
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=e.problem_code, explain=e.explain
                    )
                    if e.notify:
                        await co.send(self.__problem_report)
                    return False, None
                else:
                    await self.log(
                        progress=100, message=f'Terminated with exception',
                        exception=str(e)
                    )
                    raise
            else:
                return True, ledger

    async def accept_microledger(self, leader: Pairwise, propose: InitRequestLedgerMessage) -> (bool, Microledger):
        if self.me.did not in propose.participants:
            raise SiriusContextError('Invalid state machine initialization')
        time_to_live = propose.timeout_sec or self.time_to_live
        await self._bootstrap(propose.participants)
        async with self.leader(their=leader, thread_id=propose.thread_id, time_to_live=time_to_live) as co:
            ledger_name = propose.ledger.get('name', None)
            try:
                if not ledger_name:
                    raise StateMachineTerminatedWithError(
                        problem_code=REQUEST_PROCESSING_ERROR,
                        explain='Ledger name is Empty!',
                    )
                for their_did in propose.participants:
                    if their_did != self.me.did:
                        pw = self.__cached_p2p.get(their_did, None)
                        if pw is None:
                            raise StateMachineTerminatedWithError(
                                problem_code=REQUEST_PROCESSING_ERROR,
                                explain=f'Pairwise for DID: "their_did" does not exists!' % their_did
                            )
                await self.log(progress=0, message=f'Start ledger [{ledger_name}] creation process')
                ledger = await self._accept_microledger_internal(co, leader, propose, time_to_live)
                await self.log(progress=100, message='Ledger creation terminated successfully')
            except Exception as e:
                await sirius_sdk.Microledgers.reset(ledger_name)
                await self.log(message=f'Reset ledger')
                if isinstance(e, StateMachineTerminatedWithError):
                    self.__problem_report = SimpleConsensusProblemReport(e.problem_code, e.explain)
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=e.problem_code, explain=e.explain
                    )
                    if e.notify:
                        await co.send(self.__problem_report)
                    return False, None
                else:
                    await self.log(
                        progress=100, message=f'Terminated with exception',
                        exception=str(e)
                    )
                    raise
            else:
                return True, ledger

    async def commit(
            self, ledger: Microledger, participants: List[str], transactions: List[Transaction]
    ) -> (bool, Optional[List[Transaction]]):
        """
        :param ledger: Microledger instance to operate with
        :param participants: list of DIDs that present pairwise list of the Microledger relationships
                (Assumed DIDs are public or every participant has relationship with each other via pairwise)
        :param transactions: transactions to commit
        """
        await self._bootstrap(participants)
        relationships = [p2p for p2p in self.__cached_p2p.values()]
        async with self.acceptors(theirs=relationships, thread_id='simple-consensus-commit-' + uuid.uuid4().hex) as co:
            try:
                await self.log(progress=0, message=f'Start committing {len(transactions)} transactions')
                txns = await self._commit_internal(co, ledger, transactions, participants)
                await self.log(progress=100, message='Commit operation was accepted by all participants')
                return True, txns
            except Exception as e:
                await ledger.reset_uncommitted()
                await self.log(message='Reset uncommitted')
                if isinstance(e, StateMachineTerminatedWithError):
                    self.__problem_report = SimpleConsensusProblemReport(e.problem_code, e.explain)
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=e.problem_code, explain=e.explain
                    )
                    if e.notify:
                        await co.send(self.__problem_report)
                    return False, None
                else:
                    await self.log(
                        progress=100, message=f'Terminated with exception',
                        exception=str(e)
                    )
                    raise

    async def accept_commit(self, leader: Pairwise, propose: ProposeTransactionsMessage) -> bool:
        time_to_live = propose.timeout_sec or self.time_to_live
        async with self.leader(their=leader, thread_id=propose.thread_id, time_to_live=time_to_live) as co:

            ledger = None
            try:
                await self.log(progress=0, message=f'Start acception {len(propose.transactions)} transactions')
                ledger = await self._load_ledger(propose)
                await self._accept_commit_internal(co, ledger, leader, propose)
                await self.log(progress=100, message='Acception terminated successfully')
                return True

            except Exception as e:
                if ledger:
                    await ledger.reset_uncommitted()
                    await self.log(message='Reset uncommitted')
                if isinstance(e, StateMachineTerminatedWithError):
                    self.__problem_report = SimpleConsensusProblemReport(e.problem_code, e.explain)
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=e.problem_code, explain=e.explain
                    )
                    if e.notify:
                        await co.send(self.__problem_report)
                    return False
                else:
                    raise

    async def _bootstrap(self, participants: List[str]):
        for did in participants:
            if did != self.me.did:
                if did not in self.__cached_p2p:
                    p = await sirius_sdk.PairwiseList.load_for_did(did)
                    if p is None:
                        raise SiriusValidationError(f'Unknown pairwise for DID: {did}')
                    self.__cached_p2p[did] = p

    async def _load_ledger(self, propose: ProposeTransactionsMessage) -> AbstractMicroledger:
        try:
            await self._bootstrap(propose.participants)
            propose.validate()
            if len(propose.participants) < 2:
                raise SiriusValidationError(f'Stage-1: participant count less than 2')
            if self.me.did not in propose.participants:
                raise SiriusValidationError(f'Stage-1: {self.me.did} is not participant')
            is_ledger_exists = await sirius_sdk.Microledgers.is_exists(propose.state.name)
            if not is_ledger_exists:
                raise SiriusValidationError(f'Stage-1: Ledger with name {propose.state.name} does not exists')
        except SiriusValidationError as e:
            raise StateMachineTerminatedWithError(
                problem_code=RESPONSE_NOT_ACCEPTED,
                explain=e.message
            )
        ledger = await sirius_sdk.Microledgers.ledger(propose.state.name)
        return ledger

    async def _init_microledger_internal(
            self, co: CoProtocolThreadedTheirs, ledger: Microledger, participants: List[str], genesis: List[Transaction]
    ):

        # ============= STAGE 1: PROPOSE =================
        propose = InitRequestLedgerMessage(
            timeout_sec=self.time_to_live,
            ledger_name=ledger.name,
            genesis=genesis,
            root_hash=ledger.root_hash,
            participants=[did for did in participants]
        )
        await propose.add_signature(sirius_sdk.Crypto, self.me)
        request_commit = InitResponseLedgerMessage()
        request_commit.assign_from(propose)

        await self.log(progress=20, message='Send propose', payload=dict(propose))

        # Switch to await transaction acceptors action
        results = await co.switch(propose)
        await self.log(progress=30, message='Received responses from all acceptors')

        errored_acceptors_did = [pairwise.their.did for pairwise, (ok, _) in results.items() if not ok]
        if errored_acceptors_did:
            raise StateMachineTerminatedWithError(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Stage-1: Participants [%s] unreachable' % ','.join(errored_acceptors_did),
            )

        await self.log(progress=40, message='Validate responses')
        for pairwise, (_, response) in results.items():
            if isinstance(response, InitResponseLedgerMessage):
                response.validate()
                await response.check_signatures(sirius_sdk.Crypto, pairwise.their.did)
                signature = response.signature(pairwise.their.did)
                request_commit.signatures.append(signature)
            elif isinstance(response, SimpleConsensusProblemReport):
                raise StateMachineTerminatedWithError(response.problem_code, response.explain)

        # ============= STAGE 2: COMMIT ============
        await self.log(progress=60, message='Send commit request', payload=dict(request_commit))
        results = await co.switch(request_commit)
        await self.log(progress=70, message='Received commit responses')
        errored_acceptors_did = [pairwise.their.did for pairwise, (ok, _) in results.items() if not ok]
        if errored_acceptors_did:
            raise StateMachineTerminatedWithError(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Stage-2: Participants [%s] unreachable' % ','.join(errored_acceptors_did),
            )

        await self.log(progress=80, message='Validate commit responses from acceptors')
        for pairwise, (_, response) in results.items():
            if isinstance(response, SimpleConsensusProblemReport):
                raise StateMachineTerminatedWithError(
                    problem_code=RESPONSE_PROCESSING_ERROR,
                    explain=f'Participant DID: {pairwise.their.did} declined operation with error: "{response.explain}"'
                )

        # ============== STAGE 3: POST-COMMIT ============
        ack = Ack(status=Status.OK)
        await self.log(progress=90, message='All checks OK. Send Ack to acceptors')
        await co.send(ack)

    async def _accept_microledger_internal(
            self, co: CoProtocolThreadedP2P, leader: Pairwise, propose: InitRequestLedgerMessage, timeout: int
    ) -> Microledger:
        # =============== STAGE 1: PROPOSE ===============
        try:
            propose.validate()
            await propose.check_signatures(sirius_sdk.Crypto, leader.their.did)
            if len(propose.participants) < 2:
                raise SiriusValidationError('Stage-1: participants less than 2')
        except SiriusValidationError as e:
            raise StateMachineTerminatedWithError(
                REQUEST_NOT_ACCEPTED, e.message
            )
        genesis = [Transaction(txn) for txn in propose.ledger['genesis']]
        await self.log(progress=10, message='Initialize ledger')
        ledger, txns = await sirius_sdk.Microledgers.create(propose.ledger['name'], genesis)
        await self.log(progress=20, message='Ledger initialized successfully')
        if propose.ledger['root_hash'] != ledger.root_hash:
            await sirius_sdk.Microledgers.reset(ledger.name)
            raise StateMachineTerminatedWithError(REQUEST_PROCESSING_ERROR, 'Stage-1: Non-consistent Root Hash')
        response = InitResponseLedgerMessage(timeout_sec=timeout)
        response.assign_from(propose)
        commit_ledger_hash = response.ledger_hash
        await response.add_signature(sirius_sdk.Crypto, self.me)
        # =============== STAGE 2: COMMIT ===============
        await self.log(progress=30, message='Send propose response', payload=dict(response))
        ok, request_commit = await co.switch(response)
        if ok:
            await self.log(progress=50, message='Validate request commit')
            if isinstance(request_commit, InitResponseLedgerMessage):
                try:
                    request_commit.validate()
                    hashes = await request_commit.check_signatures(sirius_sdk.Crypto, participant='ALL')
                    for their_did, decoded in hashes.items():
                        if decoded != commit_ledger_hash:
                            raise SiriusValidationError(f'Stage-2: NonEqual Ledger hash with participant "{their_did}"')
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, e.message)
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
                    raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, error_explain)
                else:
                    # Accept commit
                    await self.log(progress=70, message='Send Ack')
                    ack = Ack(status=Status.OK)
                    ok, resp = await co.switch(ack)
                    # =========== STAGE-3: POST-COMMIT ===============
                    if ok:
                        await self.log(progress=90, message='Response to Ack received')
                        if isinstance(resp, Ack):
                            return ledger
                        elif isinstance(resp, SimpleConsensusProblemReport):
                            self.__problem_report = resp
                            logging.error(
                                'Code: %s; Explain: %s' % (resp.problem_code, resp.explain))
                            raise StateMachineTerminatedWithError(
                                self.__problem_report.problem_code, self.__problem_report.explain
                            )
                    else:
                        raise StateMachineTerminatedWithError(
                            problem_code=REQUEST_PROCESSING_ERROR,
                            explain='Stage-3: Commit accepting was terminated by timeout for actor: %s' % leader.their.did
                        )
            elif isinstance(request_commit, SimpleConsensusProblemReport):
                self.__problem_report = request_commit
                raise StateMachineTerminatedWithError(
                    self.__problem_report.problem_code, self.__problem_report.explain
                )
        else:
            raise StateMachineTerminatedWithError(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Stage-2: Commit response awaiting was terminated by timeout for actor: %s' % leader.their.did,
            )

    async def _commit_internal(
            self, co: CoProtocolThreadedTheirs, ledger: Microledger, transactions: List[Transaction], participants: List[str]
    ) -> List[Transaction]:

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
        await self_pre_commit.sign_state(sirius_sdk.Crypto, self.me)
        commit.add_pre_commit(
            participant=self.me.did,
            pre_commit=self_pre_commit
        )

        await self.log(progress=20, message='Send Propose to participants', payload=dict(propose))
        results = await co.switch(propose)
        await self.log(progress=30, message='Received Propose from participants')

        errored_acceptors_did = [pairwise.their.did for pairwise, (ok, _) in results.items() if not ok]
        if errored_acceptors_did:
            raise StateMachineTerminatedWithError(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Stage-1: Participants [%s] unreachable' % ','.join(errored_acceptors_did),
            )

        await self.log(progress=50, message='Validate responses')
        for pairwise, (_, pre_commit) in results.items():
            if isinstance(pre_commit, PreCommitTransactionsMessage):
                try:
                    pre_commit.validate()
                    success, state = await pre_commit.verify_state(sirius_sdk.Crypto, pairwise.their.verkey)
                    if not success:
                        raise SiriusValidationError(
                            f'Stage-1: Error verifying signed ledger state for participant {pairwise.their.did}'
                        )
                    if pre_commit.hash != propose.state.hash:
                        raise SiriusValidationError(
                            f'Stage-1: Non-consistent ledger state for participant {pairwise.their.did}'
                        )
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(
                        problem_code=RESPONSE_NOT_ACCEPTED,
                        explain=f'Stage-1: Error for participant {pairwise.their.did}: "{e.message}"'
                    )
                else:
                    commit.add_pre_commit(pairwise.their.did, pre_commit)
            elif isinstance(pre_commit, SimpleConsensusProblemReport):
                explain = f'Stage-1: Problem report from participant {pairwise.their.did} "{pre_commit.explain}"'
                raise StateMachineTerminatedWithError(
                    self.__problem_report.problem_code, self.__problem_report.explain
                )

        # ===== STAGE-2: Accumulate pre-commits and send commit propose to all participants
        post_commit_all = PostCommitTransactionsMessage()
        await post_commit_all.add_commit_sign(sirius_sdk.Crypto, commit, self.me)

        await self.log(progress=60, message='Send Commit to participants', payload=dict(commit))
        results = await co.switch(commit)
        await self.log(progress=70, message='Received Commit response from participants')

        errored_acceptors_did = [pairwise.their.did for pairwise, (ok, _) in results.items() if not ok]
        if errored_acceptors_did:
            raise StateMachineTerminatedWithError(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Stage-2: Participants [%s] unreachable' % ','.join(errored_acceptors_did),
            )

        await self.log(progress=80, message='Validate responses')
        for pairwise, (_, post_commit) in results.items():
            if isinstance(post_commit, PostCommitTransactionsMessage):
                try:
                    post_commit.validate()
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(
                        problem_code=RESPONSE_NOT_ACCEPTED,
                        explain=f'Stage-2: Error for participant {pairwise.their.did}: "{e.message}"',
                    )
                else:
                    post_commit_all['commits'].extend(post_commit.commits)
            elif isinstance(post_commit, SimpleConsensusProblemReport):
                raise StateMachineTerminatedWithError(
                    problem_code=self.__problem_report.problem_code,
                    explain=f'Stage-2: Problem report from participant {pairwise.their.did} "{post_commit.explain}"'
                )

        # ===== STAGE-3: Notify all participants with post-commits and finalize process
        await self.log(progress=90, message='Send Post-Commit', payload=dict(post_commit_all))
        await co.send(post_commit_all)
        uncommitted_size = ledger.uncommitted_size - ledger.size
        await ledger.commit(uncommitted_size)
        return txns

    async def _accept_commit_internal(
            self, co: CoProtocolThreadedP2P, ledger: AbstractMicroledger,
            leader: Pairwise, propose: ProposeTransactionsMessage
    ):
        # ===== STAGE-1: Process Propose, apply transactions and response ledger state on self-side
        await ledger.append(propose.transactions)
        ledger_state = MicroLedgerState.from_ledger(ledger)
        pre_commit = PreCommitTransactionsMessage(state=MicroLedgerState.from_ledger(ledger))
        await pre_commit.sign_state(sirius_sdk.Crypto, self.me)
        await self.log(progress=10, message='Send Pre-Commit', payload=dict(pre_commit))

        ok, commit = await co.switch(pre_commit)
        if ok:
            await self.log(progress=20, message='Received Pre-Commit response', payload=dict(commit))
            if isinstance(commit, CommitTransactionsMessage):
                # ===== STAGE-2: Process Commit request, check neighbours signatures
                try:
                    await self.log(progress=30, message='Validate Commit')
                    if set(commit.participants) != set(propose.participants):
                        raise SiriusValidationError('Non-consistent participants')
                    commit.validate()
                    await commit.verify_pre_commits(sirius_sdk.Crypto, ledger_state)
                except SiriusValidationError as e:
                    raise StateMachineTerminatedWithError(
                        problem_code=REQUEST_NOT_ACCEPTED,
                        explain=f'Stage-2: error for actor {leader.their.did}: "{e.message}"'
                    )
                else:
                    # ===== STAGE-3: Process post-commit, verify participants operations
                    post_commit = PostCommitTransactionsMessage()
                    await post_commit.add_commit_sign(sirius_sdk.Crypto, commit, self.me)

                    await self.log(progress=50, message='Send Post-Commit', payload=dict(post_commit))
                    ok, post_commit_all = await co.switch(post_commit)
                    if ok:
                        await self.log(
                            progress=60, message='Received Post-Commit response', payload=dict(post_commit_all)
                        )
                        if isinstance(post_commit_all, PostCommitTransactionsMessage):
                            try:

                                await self.log(progress=80, message='Validate response')
                                post_commit_all.validate()

                                verkeys = [p2p.their.verkey for p2p in self.__cached_p2p.values()]
                                await post_commit_all.verify_commits(sirius_sdk.Crypto, commit, verkeys)

                            except SiriusValidationError as e:
                                raise StateMachineTerminatedWithError(
                                    problem_code=REQUEST_NOT_ACCEPTED,
                                    explain=f'Stage-3: error for leader {leader.their.did}: "{e.message}"'
                                )
                            else:
                                uncommitted_size = ledger_state.uncommitted_size - ledger_state.size
                                await self.log(progress=90, message='Flush transactions to Ledger storage')
                                await ledger.commit(uncommitted_size)
                        elif isinstance(post_commit_all, SimpleConsensusProblemReport):
                            raise StateMachineTerminatedWithError(
                                problem_code=self.__problem_report.problem_code,
                                explain=f'Stage-3: Problem report from leader {leader.their.did}: "{post_commit_all.explain}"'
                            )
                    else:
                        raise StateMachineTerminatedWithError(
                            problem_code=REQUEST_PROCESSING_ERROR,
                            explain=f'Stage-3: Post-Commit awaiting terminated by timeout for leader: {leader.their.did}'
                        )
            elif isinstance(commit, SimpleConsensusProblemReport):
                explain = f'Stage-1: Problem report from leader {leader.their.did}: "{commit.explain}"'
                self.__problem_report = SimpleConsensusProblemReport(commit.problem_code, explain)
                raise StateMachineTerminatedWithError(
                    problem_code=self.__problem_report.problem_code, explain=self.__problem_report.explain
                )
            else:
                raise StateMachineTerminatedWithError(
                    problem_code=REQUEST_NOT_ACCEPTED, explain='Unexpected message @type: %s' % (str(commit.type))
                )
        else:
            raise StateMachineTerminatedWithError(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain=f'Stage-1: Commit awaiting terminated by timeout for leader: {leader.their.did}'
            )
