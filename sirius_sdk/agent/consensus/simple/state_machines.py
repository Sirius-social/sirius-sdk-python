import uuid
import logging
from typing import List

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

        ledger, txns = await self.microledgers.create(ledger_name, genesis)
        try:
            operation_thread_id = uuid.uuid4().hex
            p2p = {}
            participants = list(set(participants + [self.me.did]))
            for did in participants:
                if did != self.me.did:
                    their_did = did
                    pw = await self.pairwise_list.load_for_did(their_did)
                    if pw is None:
                        raise SiriusContextError('Pairwise for DID "%s" does not exists' % did)
                    transport = await self.transports.spawn(operation_thread_id, pw)
                    await transport.start()
                    p2p[their_did] = transport
            try:
                # ============= STAGE 1: PROPOSE =================
                propose = InitRequestLedgerMessage(
                    ledger_name=ledger_name,
                    genesis=txns,
                    root_hash=ledger.root_hash,
                    participants=[did for did in participants]
                )
                await propose.add_signature(self.crypto, self.me)
                accum = InitResponseLedgerMessage()
                accum.assign_from(propose)
                for their_did, transport in p2p.items():
                    ok, response = await transport.switch(propose)
                    if ok:
                        if isinstance(response, InitResponseLedgerMessage):
                            response.validate()
                            await response.check_signatures(self.crypto, their_did)
                            signature = response.signature(their_did)
                            accum.signatures.append(signature)
                        elif isinstance(response, SimpleConsensusProblemReport):
                            self.__problem_report = response
                            logging.error('Code: %s; Explain: %s' % (response.problem_code, response.explain))
                            return False, None
                    else:
                        self.__problem_report = SimpleConsensusProblemReport(
                            problem_code=RESPONSE_PROCESSING_ERROR,
                            explain='Stage1: Response awaiting was terminated by timeout for participant: %s' % their_did,
                            thread_id=operation_thread_id
                        )
                        await transport.send(self.__problem_report)
                        return False, None
                # ============= STAGE 2: PRE-COMMIT ============
                for their_did, transport in p2p.items():
                    print('$')
                    ok, response = await transport.switch(accum)
                    print('@')

            finally:
                for transport in p2p.values():
                    await transport.stop()
        except:
            await self.microledgers.reset(ledger_name)

    async def accept_microledger(self, actor: Pairwise, propose: InitRequestLedgerMessage) -> (bool, Microledger):
        operation_thread_id = propose.thread_id
        transport = await self.transports.spawn(operation_thread_id, actor)
        await transport.start()
        try:
            # =============== STAGE 1: PROPOSE ===============
            propose.validate()
            await propose.check_signatures(self.crypto, actor.their.did)
            if len(propose.participants) < 2:
                error = 'Stage1: participants less than 2'
            elif actor.me.did not in propose.participants:
                error = 'Stage1: participants less than 2'
            else:
                error = None
                for their_did in [did for did in propose.participants if did != actor.me.did]:
                    exists = await self.pairwise_list.is_exists(their_did)
                    if not exists:
                        error = 'Pairwise for did: %d does not Exists. We should have preconfigured pairwise list' % their_did
                        break
                if not error:
                    genesis = [Transaction(txn) for txn in propose.ledger['genesis']]
                    ledger, txns = await self.microledgers.create(propose.ledger['name'], genesis)
                    if propose.ledger['root_hash'] != ledger.root_hash:
                        error = 'Non-consistent Root Hash'
                        self.microledgers.reset(ledger.name)
            if error:
                self.__problem_report = SimpleConsensusProblemReport(
                    problem_code=REQUEST_PROCESSING_ERROR,
                    explain='Stage1: Response awaiting was terminated by timeout for participant: %s' % their_did,
                    thread_id=operation_thread_id
                )
                await transport.send(self.__problem_report)
                return False, None
            response = InitResponseLedgerMessage()
            response.assign_from(propose)
            await response.add_signature(self.crypto, self.me)
            ok, accum_proposed = await transport.switch(response)
            if ok:
                # =============== STAGE 2: PRE-COMMIT ===============
                # if accum_proposed
                pass
            else:
                'TODO'
                pass
        finally:
            await transport.stop()

    def _terminate_with_problem_report(self, problem_code: str, explain, thread_id: str, raise_exception: bool=True):
        self.__problem_report = SimpleConsensusProblemReport(
            problem_code=problem_code, explain=explain, thread_id=thread_id
        )
        if raise_exception:
            raise self.__problem_report

    async def _init_microledger_internal(self, ledger: Microledger, participants: List[str], genesis: List[Transaction]):
        try:
            operation_thread_id = uuid.uuid4().hex
            p2p = {}
            participants = list(set(participants + [self.me.did]))
            for did in participants:
                if did != self.me.did:
                    their_did = did
                    pw = await self.pairwise_list.load_for_did(their_did)
                    if pw is None:
                        raise SiriusContextError('Pairwise for DID "%s" does not exists' % did)
                    transport = await self.transports.spawn(operation_thread_id, pw)
                    await transport.start()
                    p2p[their_did] = transport
            try:
                # ============= STAGE 1: PROPOSE =================
                propose = InitRequestLedgerMessage(
                    ledger_name=ledger_name,
                    genesis=txns,
                    root_hash=ledger.root_hash,
                    participants=[did for did in participants]
                )
                await propose.add_signature(self.crypto, self.me)
                accum = InitResponseLedgerMessage()
                accum.assign_from(propose)
                for their_did, transport in p2p.items():
                    ok, response = await transport.switch(propose)
                    if ok:
                        if isinstance(response, InitResponseLedgerMessage):
                            response.validate()
                            await response.check_signatures(self.crypto, their_did)
                            signature = response.signature(their_did)
                            accum.signatures.append(signature)
                        elif isinstance(response, SimpleConsensusProblemReport):
                            self.__problem_report = response
                            logging.error('Code: %s; Explain: %s' % (response.problem_code, response.explain))
                            return False, None
                    else:
                        self.__problem_report = SimpleConsensusProblemReport(
                            problem_code=RESPONSE_PROCESSING_ERROR,
                            explain='Stage1: Response awaiting was terminated by timeout for participant: %s' % their_did,
                            thread_id=operation_thread_id
                        )
                        await transport.send(self.__problem_report)
                        return False, None
                # ============= STAGE 2: PRE-COMMIT ============
                for their_did, transport in p2p.items():
                    print('$')
                    ok, response = await transport.switch(accum)
                    print('@')

            finally:
                for transport in p2p.values():
                    await transport.stop()
        except:
            await self.microledgers.reset(ledger_name)

    async def commit(
            self, ledger: Microledger, transactions: List[Transaction]
    ) -> (bool, List[Transaction]):
        pass

    async def accept_commit(self, actor: Pairwise, ledger: Microledger, transactions: List[Transaction]) -> bool:
        pass
