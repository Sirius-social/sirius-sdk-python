import uuid
import logging
from datetime import datetime
from typing import List, Union, Tuple

from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.agent.wallet.abstract.crypto import AbstractCrypto
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.agent.microledgers import Transaction, Microledger, MicroledgerList
from sirius_sdk.agent.sm import AbstractStateMachine, StateMachineTerminatedWithError, StateMachineAborted
from sirius_sdk.agent.aries_rfc.feature_0015_acks import Ack, Status
from sirius_sdk.agent.consensus.simple.messages import *

# Problem codes
REQUEST_NOT_ACCEPTED = "request_not_accepted"
REQUEST_PROCESSING_ERROR = 'request_processing_error'
RESPONSE_NOT_ACCEPTED = "response_not_accepted"
RESPONSE_PROCESSING_ERROR = 'response_processing_error'


class MicroLedgerSimpleConsensus(AbstractStateMachine):

    def __init__(
            self, me: Pairwise.Me,
            crypto: AbstractCrypto = None, pairwise_list: AbstractPairwiseList = None,
            microledgers: MicroledgerList = None, *args, **kwargs
    ):
        self.__me = me
        self.__problem_report = None
        self.__microledgers = microledgers
        self.__microledgers_internal = microledgers is None
        self.__crypto = crypto
        self.__crypto_internal = crypto is None
        self.__pairwise_list = pairwise_list
        self.__pairwise_list_internal = pairwise_list is None
        self.__transport = None
        self.__thread_id = None
        self.__cached_p2p = {}
        self.__neighbours = []
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
            self.__neighbours = [did for did in participants if did != self.me.did]
            await self.log(progress=0, message=f'Create ledger [{ledger_name}]')
            ledger, genesis = await self.microledgers.create(ledger_name, genesis)
            await self.log(message=f'Ledger creation terminated successfully')
            try:
                await self._init_microledger_internal(ledger, participants, genesis)
                await self.log(progress=100, message='All participants accepted ledger creation')
            except Exception as e:
                await self.microledgers.reset(ledger_name)
                await self.log(message=f'Reset ledger')
                if isinstance(e, StateMachineTerminatedWithError):
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=e.problem_code, explain=e.explain
                    )
                    return False, None
                else:
                    await self.log(
                        progress=100, message=f'Terminated with exception',
                        exception=str(e)
                    )
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
            self.__neighbours = [did for did in propose.participants if did != self.me.did]
            ledger_name = propose.ledger.get('name', None)
            try:
                if not ledger_name:
                    await self._terminate_with_problem_report(
                        problem_code=REQUEST_PROCESSING_ERROR,
                        explain='Ledger name is Empty!',
                        their_did=actor.their.did,
                    )
                for their_did in propose.participants:
                    if their_did != self.me.did:
                        pw = await self.get_p2p(their_did, raise_exception=False)
                        if pw is None:
                            await self._terminate_with_problem_report(
                                problem_code=REQUEST_PROCESSING_ERROR,
                                explain=f'Pairwise for DID: "their_did" does not exists!' % their_did,
                                their_did=actor.their.did
                            )
                await self.log(progress=0, message=f'Start ledger [{ledger_name}] creation process')
                ledger = await self._accept_microledger_internal(actor, propose, time_to_live)
                await self.log(progress=100, message='Ledger creation terminated successfully')
            except Exception as e:
                await self.microledgers.reset(ledger_name)
                await self.log(message=f'Reset ledger')
                if isinstance(e, StateMachineTerminatedWithError):
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=e.problem_code, explain=e.explain
                    )
                    return False, None
                else:
                    await self.log(
                        progress=100, message=f'Terminated with exception',
                        exception=str(e)
                    )
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
            self.__neighbours = [did for did in participants if did != self.me.did]
            try:
                await self.log(progress=0, message=f'Start committing {len(transactions)} transactions')
                txns = await self._commit_internal(ledger, transactions, participants)
                await self.log(progress=100, message='Commit operation was accepted by all participants')
                return True, txns
            except Exception as e:
                await ledger.reset_uncommitted()
                await self.log(message='Reset uncommitted')
                if isinstance(e, StateMachineTerminatedWithError):
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=e.problem_code, explain=e.explain
                    )
                    return False, None
                else:
                    await self.log(
                        progress=100, message=f'Terminated with exception',
                        exception=str(e)
                    )
                    raise
        finally:
            await self._clean()

    async def accept_commit(self, actor: Pairwise, propose: ProposeTransactionsMessage) -> bool:
        time_to_live = propose.timeout_sec or self.time_to_live
        await self._setup(propose.thread_id, time_to_live)
        try:
            ledger = None
            self.__neighbours = [did for did in propose.participants if did != self.me.did]
            try:
                await self.log(progress=0, message=f'Start acception {len(propose.transactions)} transactions')
                ledger = await self._load_ledger(actor, propose)
                await self._accept_commit_internal(ledger, actor, propose)
                await self.log(progress=100, message='Acception terminated successfully')
                return True
            except Exception as e:
                if ledger:
                    await ledger.reset_uncommitted()
                    await self.log(message='Reset uncommitted')
                if isinstance(e, StateMachineTerminatedWithError):
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=e.problem_code, explain=e.explain
                    )
                    await self.log(
                        progress=100, message=f'Terminated with exception',
                        exception=str(e)
                    )
                    return False
                else:
                    raise
        finally:
            await self._clean()

    async def abort(self):
        await super().abort()
        if self.__transport and self.__transport.is_started:
            await self._terminate_with_problem_report(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Operation is aborted by owner',
                their_did=self.__neighbours
            )

    async def _switch(
            self, their_did: str, req: Union[SimpleConsensusMessage, SimpleConsensusProblemReport, Ack]
    ) -> (bool, Union[SimpleConsensusMessage, SimpleConsensusProblemReport]):
        if isinstance(req, SimpleConsensusMessage) or isinstance(req, SimpleConsensusProblemReport) or isinstance(req, Ack):
            pw = await self.get_p2p(their_did)
            self.__transport.pairwise = pw
            ok, resp = await self.__transport.switch(req)
            if self.is_aborted:
                await self.log(progress=100, message='Aborted')
                raise StateMachineAborted
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
            pw = await self.get_p2p(their_did)
            self.__transport.pairwise = pw
            await self.__transport.send(message)
        elif isinstance(their_did, list):
            tos = [await self.get_p2p(did) for did in their_did]
            await self.__transport.send_many(message, tos)
        else:
            raise SiriusContextError('Unexpected their_did type')

    async def _switch_multiple(
            self, their_did: List[str], message: AriesProtocolMessage
    ) -> List[Tuple[bool, AriesProtocolMessage]]:
        tos = [await self.get_p2p(did) for did in their_did]
        vk2did = {p.their.verkey: p.their.did for p in tos}
        responses = await self.__transport.send_many(message, tos)
        results = []
        await_list = {}
        for did, response in zip(their_did, responses):
            success, body = response
            item = (success, None)
            results.append(item)
            if success:
                await_list[did] = None
        if await_list:
            for n in range(len(await_list)):
                message, sender_verkey, recipient_verkey = await self.__transport.get_one()
                did = vk2did[sender_verkey]
                await_list[did] = message
            for i, did in enumerate(their_did):
                success, body = results[i]
                if success is True:
                    msg = await_list.get(did, None)
                    results[i] = (success, msg)
            return results
        else:
            return []

    async def _setup(self, thread_id: str, time_to_live: int):
        self.__thread_id = thread_id
        self.__transport = await self.transports.spawn(thread_id)
        await self.__transport.start(time_to_live=time_to_live)
        if self.__microledgers_internal:
            self.__microledgers = self.__transport.microledgers
        if self.__crypto_internal:
            self.__crypto = self.__transport.wallet.crypto
        if self.__pairwise_list_internal:
            self.__pairwise_list = self.__transport.pairwise_list

    async def _clean(self):
        if self.__transport:
            await self.__transport.stop()
        self.__transport = None
        if self.__microledgers_internal:
            self.__microledgers = None
        if self.__crypto_internal:
            self.__crypto = None
        if self.__pairwise_list_internal:
            self.__pairwise_list = None

    async def get_p2p(self, their_did: str, raise_exception: bool = True) -> Pairwise:
        if their_did not in self.__cached_p2p.keys():
            pw = await self.pairwise_list.load_for_did(their_did)
            if pw is None and raise_exception:
                raise SiriusContextError('Pairwise for "%s" does not exists!' % their_did)
            self.__cached_p2p[their_did] = pw
        return self.__cached_p2p[their_did]

    async def _terminate_with_problem_report(
            self, problem_code: str, explain, their_did: Union[str, List[str]], raise_exception: bool = True
    ):
        self.__problem_report = SimpleConsensusProblemReport(
            problem_code=problem_code, explain=explain, thread_id=self.__thread_id
        )
        if isinstance(their_did, str):
            await self._send(their_did, self.__problem_report)
        elif isinstance(their_did, list):
            await self._send(their_did, self.__problem_report)
        else:
            raise SiriusContextError('Unexpected their_did type')
        if raise_exception:
            raise StateMachineTerminatedWithError(problem_code, explain)

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

        await self.log(progress=20, message='Send propose', payload=dict(propose))
        results = await self._switch_multiple(neighbours, propose)
        await self.log(progress=30, message='Received responses from all participants')
        neighbours_responses = {did: msg for (ok, msg), did in zip(results, neighbours) if ok is True}
        if len(neighbours) != len(neighbours):
            error_neighbours = [did for (ok, _), did in zip(results, neighbours) if not ok]
            await self._terminate_with_problem_report(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Stage-1: Participants [%s] unreachable' % ','.join(error_neighbours),
                their_did=neighbours
            )

        await self.log(progress=40, message='Validate responses')
        for their_did, response in neighbours_responses.items():
            if isinstance(response, InitResponseLedgerMessage):
                response.validate()
                await response.check_signatures(self.crypto, their_did)
                signature = response.signature(their_did)
                request_commit.signatures.append(signature)
            elif isinstance(response, SimpleConsensusProblemReport):
                self.__problem_report = response
                logging.error('Code: %s; Explain: %s' % (response.problem_code, response.explain))
                raise StateMachineTerminatedWithError(response.problem_code, response.explain)

        # ============= STAGE 2: COMMIT ============
        await self.log(progress=60, message='Send commit request', payload=dict(request_commit))
        results = await self._switch_multiple(neighbours, request_commit)
        await self.log(progress=70, message='Received commit responses')
        neighbours_responses = {did: msg for (ok, msg), did in zip(results, neighbours) if ok is True}

        await self.log(progress=80, message='Validate commit responses from neighbours')
        acks = []
        for their_did, response in neighbours_responses.items():
            if isinstance(response, SimpleConsensusProblemReport):
                neighbours = [did for did in neighbours if did != their_did]
                await self._terminate_with_problem_report(response.problem_code, response.explain, neighbours)
            else:
                acks.append(their_did)
        # ============== STAGE 3: POST-COMMIT ============
        if set(acks) == set(neighbours):
            ack = Ack(thread_id=self.__thread_id, status=Status.OK)
            await self.log(progress=90, message='All checks OK. Send Ack to neighbors')
            await self._send(neighbours, ack)
        else:
            acks_str = ','.join(acks)
            neighbours_str = ','.join(neighbours)
            await self._terminate_with_problem_report(
                REQUEST_PROCESSING_ERROR,
                f'Stage-3: Actual list of acceptors: [{acks_str}]  Expected: [{neighbours_str}]',
                neighbours
            )

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
        await self.log(progress=10, message='Initialize ledger')
        ledger, txns = await self.microledgers.create(propose.ledger['name'], genesis)
        await self.log(progress=20, message='Ledger initialized successfully')
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
        await self.log(progress=30, message='Send propose response', payload=dict(response))
        ok, request_commit = await self._switch(actor.their.did, response)
        if ok:
            await self.log(progress=50, message='Validate request commit')
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
                    await self.log(progress=70, message='Send Ack')
                    ack = Ack(thread_id=self.__thread_id, status=Status.OK)
                    ok, resp = await self._switch(actor.their.did, ack)
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
                        await self._terminate_with_problem_report(
                            problem_code=REQUEST_PROCESSING_ERROR,
                            explain='Stage-3: Commit accepting was terminated by timeout for actor: %s' % actor.their.did,
                            their_did=actor.their.did
                        )
            elif isinstance(request_commit, SimpleConsensusProblemReport):
                self.__problem_report = request_commit
                raise StateMachineTerminatedWithError(
                    self.__problem_report.problem_code, self.__problem_report.explain
                )
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
        await self.log(progress=20, message='Send Propose to participants', payload=dict(propose))
        results = await self._switch_multiple(neighbours, propose)
        await self.log(progress=30, message='Received Propose from participants')
        neighbours_responses = {did: msg for (ok, msg), did in zip(results, neighbours) if ok is True}
        if len(neighbours) != len(neighbours):
            error_neighbours = [did for (ok, _), did in zip(results, neighbours) if not ok]
            await self._terminate_with_problem_report(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Stage-1: Participants [%s] unreachable' % ','.join(error_neighbours),
                their_did=neighbours
            )

        await self.log(progress=50, message='Validate responses')
        for their_did, pre_commit in neighbours_responses.items():
            if isinstance(pre_commit, PreCommitTransactionsMessage):
                try:
                    pre_commit.validate()
                    success, state = await pre_commit.verify_state(self.crypto, verkeys[their_did])
                    if not success:
                        raise SiriusValidationError(
                            f'Stage-1: Error verifying signed ledger state for participant {their_did}'
                        )
                    if pre_commit.hash != propose.state.hash:
                        raise SiriusValidationError(
                            f'Stage-1: Non-consistent ledger state for participant {their_did}'
                        )
                except SiriusValidationError as e:
                    await self._terminate_with_problem_report(
                        RESPONSE_NOT_ACCEPTED,
                        f'Stage-1: Error for participant {their_did}: "{e.message}"',
                        neighbours
                    )
                else:
                    commit.add_pre_commit(their_did, pre_commit)
                    awaited_list.append(their_did)
            elif isinstance(pre_commit, SimpleConsensusProblemReport):
                explain = f'Stage-1: Problem report from participant {their_did} "{pre_commit.explain}"'
                self.__problem_report = SimpleConsensusProblemReport(pre_commit.problem_code, explain)
                await self._send([did for did in neighbours if did != their_did], self.__problem_report)
                raise StateMachineTerminatedWithError(
                    self.__problem_report.problem_code, self.__problem_report.explain
                )

        # ===== STAGE-2: Accumulate pre-commits and send commit propose to all participants
        post_commit_all = PostCommitTransactionsMessage()
        await post_commit_all.add_commit_sign(self.crypto, commit, self.me)
        await self.log(progress=60, message='Send Commit to participants', payload=dict(commit))
        results = await self._switch_multiple(neighbours, commit)
        await self.log(progress=70, message='Received Commit response from participants')
        neighbours_responses = {did: msg for (ok, msg), did in zip(results, neighbours) if ok is True}
        if len(neighbours) != len(neighbours):
            error_neighbours = [did for (ok, _), did in zip(results, neighbours) if not ok]
            await self._terminate_with_problem_report(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Stage-1: Participants [%s] unreachable' % ','.join(error_neighbours),
                their_did=neighbours
            )
        await self.log(progress=80, message='Validate responses')
        for their_did, post_commit in neighbours_responses.items():
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
                raise StateMachineTerminatedWithError(
                    self.__problem_report.problem_code, self.__problem_report.explain
                )

        # ===== STAGE-3: Notify all participants with post-commits and finalize process
        await self.log(progress=90, message='Send Post-Commit', payload=dict(post_commit_all))
        await self._send(neighbours, post_commit_all)
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
        await self.log(progress=10, message='Send Pre-Commit', payload=dict(pre_commit))
        ok, commit = await self._switch(actor.their.did, pre_commit)
        if ok:
            await self.log(progress=20, message='Received Pre-Commit response', payload=dict(commit))
            if isinstance(commit, CommitTransactionsMessage):
                # ===== STAGE-2: Process Commit request, check neighbours signatures
                try:
                    await self.log(progress=30, message='Validate Commit')
                    if set(commit.participants) != set(propose.participants):
                        raise SiriusValidationError('Non-consistent participants')
                    commit.validate()
                    await commit.verify_pre_commits(self.crypto, ledger_state)
                except SiriusValidationError as e:
                    await self._terminate_with_problem_report(
                        problem_code=REQUEST_NOT_ACCEPTED,
                        explain=f'Stage-2: error for actor {actor.their.did}: "{e.message}"',
                        their_did=actor.their.did
                    )
                else:
                    # ===== STAGE-3: Process post-commit, verify participants operations
                    post_commit = PostCommitTransactionsMessage()
                    await post_commit.add_commit_sign(self.crypto, commit, self.me)

                    await self.log(progress=50, message='Send Post-Commit', payload=dict(post_commit))
                    ok, post_commit_all = await self._switch(actor.their.did, post_commit)
                    if ok:
                        await self.log(progress=60, message='Received Post-Commit response', payload=dict(post_commit_all))
                        if isinstance(post_commit_all, PostCommitTransactionsMessage):
                            try:
                                await self.log(progress=80, message='Validate response')
                                post_commit_all.validate()
                                verkeys = [(await self.get_p2p(did)).their.verkey for did in neighbours]
                                await post_commit_all.verify_commits(self.crypto, commit, verkeys)
                            except SiriusValidationError as e:
                                await self._terminate_with_problem_report(
                                    problem_code=REQUEST_NOT_ACCEPTED,
                                    explain=f'Stage-3: error for actor {actor.their.did}: "{e.message}"',
                                    their_did=actor.their.did
                                )
                            else:
                                uncommitted_size = ledger_state.uncommitted_size - ledger_state.size
                                await self.log(progress=90, message='Flush transactions to Ledger storage')
                                await ledger.commit(uncommitted_size)
                        elif isinstance(post_commit_all, SimpleConsensusProblemReport):
                            explain = f'Stage-3: Problem report from actor {actor.their.did}: "{post_commit_all.explain}"'
                            self.__problem_report = SimpleConsensusProblemReport(post_commit_all.problem_code, explain)
                            raise StateMachineTerminatedWithError(
                                self.__problem_report.problem_code, self.__problem_report.explain
                            )
                    else:
                        await self._terminate_with_problem_report(
                            problem_code=REQUEST_PROCESSING_ERROR,
                            explain=f'Stage-3: Post-Commit awaiting terminated by timeout for actor: {actor.their.did}',
                            their_did=actor.their.did
                        )
            elif isinstance(commit, SimpleConsensusProblemReport):
                explain = f'Stage-1: Problem report from actor {actor.their.did}: "{commit.explain}"'
                self.__problem_report = SimpleConsensusProblemReport(commit.problem_code, explain)
                raise StateMachineTerminatedWithError(
                    self.__problem_report.problem_code, self.__problem_report.explain
                )
            else:
                await self._terminate_with_problem_report(
                    REQUEST_NOT_ACCEPTED, 'Unexpected message @type: %s' % str(commit.type), actor.their.did
                )
        else:
            await self._terminate_with_problem_report(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain=f'Stage-1: Commit awaiting terminated by timeout for actor: {actor.their.did}',
                their_did=actor.their.did
            )
