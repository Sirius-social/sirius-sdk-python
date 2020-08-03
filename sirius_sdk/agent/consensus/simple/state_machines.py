import uuid
import logging
from typing import List, Union

from ....agent.pairwise import Pairwise
from ....agent.wallet.abstract.crypto import AbstractCrypto
from ....agent.pairwise import AbstractPairwiseList
from ....agent.microledgers import Transaction, Microledger, MicroledgerList
from ....agent.sm import AbstractStateMachine, StateMachineTerminatedWithError
from ....agent.aries_rfc.feature_0015_acks import Ack
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
        self.__p2p = {}
        self.__thread_id = None
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
        ledger, genesis = await self.microledgers.create(ledger_name, genesis)
        try:
            await self._setup(participants, 'simple-consensus-' + uuid.uuid4().hex)
            try:
                await self._init_microledger_internal(ledger, participants, genesis)
            finally:
                await self._clean()
        except Exception as e:
            await self.microledgers.reset(ledger_name)
            if isinstance(e, StateMachineTerminatedWithError):
                return False, None
        else:
            return True, ledger

    async def accept_microledger(self, actor: Pairwise, propose: InitRequestLedgerMessage) -> (bool, Microledger):
        if self.me.did not in propose.participants:
            raise SiriusContextError('Invalid state machine initialization')
        try:
            for their_did in propose.participants:
                if their_did != self.me.did:
                    if not await self.pairwise_list.is_exists(their_did):
                        await self._terminate_with_problem_report(
                            problem_code=REQUEST_PROCESSING_ERROR,
                            explain='Pairwise for DID: "" does not exists!' % their_did,
                            their_did=their_did
                        )
            await self._setup(propose.participants, propose.thread_id)
            try:
                print('#')
                ledger = await self._accept_microledger_internal(actor, propose)
                print('#')
            finally:
                await self._clean()
        except Exception as e:
            await self.microledgers.reset(propose.ledger['name'])
            if isinstance(e, StateMachineTerminatedWithError):
                return False, None
        else:
            return True, ledger

    async def _switch(
            self, their_did: str, req: Union[SimpleConsensusMessage, SimpleConsensusProblemReport]
    ) -> (bool, Union[SimpleConsensusMessage, SimpleConsensusProblemReport]):
        if isinstance(req, SimpleConsensusMessage) or isinstance(req, SimpleConsensusProblemReport):
            transport = self.__p2p.get(their_did, None)
            if transport is None:
                raise SiriusContextError('Setup state machine at first!')
            ok, resp = await transport.switch(req)
            return ok, resp
        else:
            raise SiriusContextError('Unexpected req type')

    async def _send_problem_report(self, their_did: str, report: SimpleConsensusProblemReport, thread_id: str=None):
        transport = self.__p2p.get(their_did, None)
        if transport is None:
            pw = await self.pairwise_list.load_for_did(their_did)
            if pw:
                transport = await self.transports.spawn(thread_id or self.__thread_id, pw)
                await transport.start()
                try:
                    await transport.send(report)
                finally:
                    await transport.stop()
            else:
                raise SiriusContextError('Pairwise for "%s" does not exists!' % their_did)
        await transport.send(report)

    async def _setup(self, participants: List[str], thread_id: str):
        self.__thread_id = thread_id
        for did in participants:
            if did != self.me.did:
                their_did = did
                pw = await self.pairwise_list.load_for_did(their_did)
                if pw is None:
                    raise SiriusContextError('Pairwise for DID "%s" does not exists' % did)
                transport = await self.transports.spawn(self.__thread_id, pw)
                await transport.start()
                self.__p2p[pw.their.did] = transport

    async def _clean(self):
        try:
            for transport in self.__p2p.values():
                await transport.stop()
        finally:
            self.__p2p.clear()

    async def _terminate_with_problem_report(self, problem_code: str, explain, their_did: str, raise_exception: bool=True):
        self.__problem_report = SimpleConsensusProblemReport(
            problem_code=problem_code, explain=explain, thread_id=self.__thread_id
        )
        await self._send_problem_report(their_did, self.__problem_report)
        if raise_exception:
            raise self.__problem_report

    async def _init_microledger_internal(
            self, ledger: Microledger, participants: List[str], genesis: List[Transaction]
    ):
        # ============= STAGE 1: PROPOSE =================
        propose = InitRequestLedgerMessage(
            ledger_name=ledger.name,
            genesis=genesis,
            root_hash=ledger.root_hash,
            participants=[did for did in participants]
        )
        await propose.add_signature(self.crypto, self.me)
        response_from_all = InitResponseLedgerMessage()
        response_from_all.assign_from(propose)
        neighbours = [did for did in participants if did != self.me.did]
        for their_did in neighbours:
            ok, response = await self._switch(their_did, propose)
            if ok:
                if isinstance(response, InitResponseLedgerMessage):
                    response.validate()
                    await response.check_signatures(self.crypto, their_did)
                    signature = response.signature(their_did)
                    response_from_all.signatures.append(signature)
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
        for their_did in neighbours:
            print('$')
            ok, response = await self._switch(their_did, response_from_all)
            print('@')

    async def _accept_microledger_internal(self, actor: Pairwise, propose: InitRequestLedgerMessage) -> Microledger:
        # =============== STAGE 1: PROPOSE ===============
        try:
            print('1')
            propose.validate()
            print('2')
            await propose.check_signatures(self.crypto, actor.their.did)
            print('3')
            if len(propose.participants) < 2:
                raise SiriusValidationError('Stage-1: participants less than 2')
        except SiriusValidationError as e:
            await self._terminate_with_problem_report(REQUEST_NOT_ACCEPTED, e.message, actor.their.did)
        genesis = [Transaction(txn) for txn in propose.ledger['genesis']]
        ledger, txns = await self.microledgers.create(propose.ledger['name'], genesis)
        if propose.ledger['root_hash'] != ledger.root_hash:
            await self.microledgers.reset(ledger.name)
            await self._terminate_with_problem_report(
                REQUEST_PROCESSING_ERROR, 'Non-consistent Root Hash', actor.their.did
            )
        response = InitResponseLedgerMessage()
        response.assign_from(propose)
        await response.add_signature(self.crypto, self.me)
        ok, response_from_all = await self._switch(response)
        if ok:
            # =============== STAGE 2: COMMIT ===============
            # if accum_proposed
            if isinstance(response_from_all, InitResponseLedgerMessage):
                pass
        else:
            'TODO'
            pass

    async def commit(
            self, ledger: Microledger, transactions: List[Transaction]
    ) -> (bool, List[Transaction]):
        pass

    async def accept_commit(self, actor: Pairwise, ledger: Microledger, transactions: List[Transaction]) -> bool:
        pass
