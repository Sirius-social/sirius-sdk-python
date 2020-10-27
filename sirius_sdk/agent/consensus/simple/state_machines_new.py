import uuid
import logging
import contextlib
from datetime import datetime
from typing import Union, Tuple

import sirius_sdk
from sirius_sdk.agent.pairwise import AbstractPairwiseList
from sirius_sdk.agent.microledgers import MicroledgerList
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
        self.__neighbours = []

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
        relationships = [p2p for p2p in self.__cached_p2p]
        async with self.acceptors(theirs=relationships, thread_id='simple-consensus-' + uuid.uuid4().hex) as co:
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
                    self.__problem_report = SimpleConsensusProblemReport(
                        e.problem_code, e.explain
                    )
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
        relationships = [p2p for p2p in self.__cached_p2p]
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
                        pw = await self.__cached_p2p.get(their_did, None)
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
                    self.__problem_report = SimpleConsensusProblemReport(
                        e.problem_code, e.explain
                    )
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

    async def _bootstrap(self, participants: List[str]):
        for did in participants:
            if did != self.me.did:
                if did not in self.__cached_p2p:
                    p = await sirius_sdk.PairwiseList.load_for_did(did)
                    if p is None:
                        raise SiriusContextError(f'Unknown pairwise for DID: {did}')
                    self.__cached_p2p[did] = p

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

        errored_acceptors_did = [pairwise.their.did for pairwise, (ok, _) in results if not ok]
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
        errored_acceptors_did = [pairwise.their.did for pairwise, (ok, _) in results if not ok]
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
