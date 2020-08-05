import uuid
import logging
from typing import List, Union

from ....agent.pairwise import Pairwise
from ....agent.wallet.abstract.crypto import AbstractCrypto
from ....agent.pairwise import AbstractPairwiseList
from ....agent.microledgers import Transaction, Microledger, MicroledgerList
from ....agent.sm import AbstractStateMachine, StateMachineTerminatedWithError
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
                if isinstance(e, StateMachineTerminatedWithError):
                    return False, None
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
            self.__thread_id = propose.thread_id
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
                if isinstance(e, StateMachineTerminatedWithError):
                    return False, None
            else:
                return True, ledger
        finally:
            await self._clean()

    async def _switch(
            self, their_did: str, req: Union[SimpleConsensusMessage, SimpleConsensusProblemReport, Ack]
    ) -> (bool, Union[SimpleConsensusMessage, SimpleConsensusProblemReport]):
        if isinstance(req, SimpleConsensusMessage) or isinstance(req, SimpleConsensusProblemReport) or isinstance(req, Ack):
            pw = await self.get_p2p(their_did)
            self.__transport.pairwise = pw
            ok, resp = await self.__transport.switch(req)
            return ok, resp
        else:
            raise SiriusContextError('Unexpected req type')

    async def _send(self, their_did: str, message: AriesProtocolMessage, thread_id: str=None):
        pw = await self.get_p2p(their_did)
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

    async def get_p2p(self, their_did: str, raise_exception: bool = True):
        if their_did not in self.__cached_p2p.keys():
            pw = await self.pairwise_list.load_for_did(their_did)
            if pw is None and raise_exception:
                raise SiriusContextError('Pairwise for "%s" does not exists!' % their_did)
            self.__cached_p2p[their_did] = pw
        return self.__cached_p2p[their_did]

    async def _terminate_with_problem_report(self, problem_code: str, explain, their_did: str, raise_exception: bool=True):
        self.__problem_report = SimpleConsensusProblemReport(
            problem_code=problem_code, explain=explain, thread_id=self.__thread_id
        )
        await self._send(their_did, self.__problem_report)
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
                logging.error('Code: %s; Explain: %s' % (request_commit.problem_code, request_commit.explain))
                raise self.__problem_report
        else:
            await self._terminate_with_problem_report(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Stage-2: Commit response awaiting was terminated by timeout for actor: %s' % actor.their.did,
                their_did=actor.their.did
            )

    async def commit(
            self, ledger: Microledger, transactions: List[Transaction]
    ) -> (bool, List[Transaction]):
        pass

    async def accept_commit(self, actor: Pairwise, ledger: Microledger, transactions: List[Transaction]) -> bool:
        pass
