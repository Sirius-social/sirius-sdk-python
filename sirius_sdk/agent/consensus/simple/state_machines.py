import uuid
import logging
from typing import List

from ....agent.pairwise import Pairwise
from ....agent.wallet.abstract.crypto import AbstractCrypto
from ....agent.microledgers import Transaction, Microledger, MicroledgerList
from ....agent.sm import AbstractStateMachine
from ....agent.aries_rfc.feature_0015_acks import Ack
from .messages import *

# Problem codes
REQUEST_NOT_ACCEPTED = "request_not_accepted"
REQUEST_PROCESSING_ERROR = 'request_processing_error'
RESPONSE_NOT_ACCEPTED = "response_not_accepted"
RESPONSE_PROCESSING_ERROR = 'response_processing_error'


class MicroLedgerSimpleConsensus(AbstractStateMachine):

    def __init__(self, crypto: AbstractCrypto, me: Pairwise.Me, service: MicroledgerList, *args, **kwargs):
        self.__me = me
        self.__problem_report = None
        self.__service = service
        self.__crypto = crypto
        super().__init__(*args, **kwargs)

    @property
    def me(self) -> Pairwise.Me:
        return self.__me

    @property
    def crypto(self) -> AbstractCrypto:
        return self.__crypto

    @property
    def service(self) -> MicroledgerList:
        return self.__service

    @property
    def protocols(self) -> List[str]:
        return [SimpleConsensusMessage.PROTOCOL, Ack.PROTOCOL]

    @property
    def problem_report(self) -> SimpleConsensusProblemReport:
        return self.__problem_report

    async def init_microledger(
            self, ledger_name: str, participants: List[Pairwise], genesis: List[Transaction]
    ) -> (bool, Microledger):

        ledger, txns = await self.service.create(ledger_name, genesis)
        operation_thread_id = uuid.uuid4().hex
        p2p = {}
        for p in participants:
            p2p[p.their.did] = await self.transports.spawn(operation_thread_id, p)
        try:
            # STAGE 1: PROPOSE
            propose = InitRequestLedgerMessage(
                ledger_name=ledger_name,
                genesis=txns,
                root_hash=ledger.root_hash,
                participants=[p.their.did for p in participants] + [self.me.did]
            )
            await propose.add_signature(self.crypto, self.me)
            accum = InitResponseLedgerMessage()
            accum.assign_from(propose)
            for their_did, transport in p2p.items():
                response = await transport.switch(propose)
                if isinstance(response, InitResponseLedgerMessage):
                    response.validate()
                    await response.check_signatures(self.crypto, their_did)
                elif isinstance(response, SimpleConsensusProblemReport):
                    self.__problem_report = response
                    logging.error('Code: %s; Explain: %s' % (response.problem_code, response.explain))
                    return False, None
            # STAGE 2: PRE-COMMIT
        finally:
            for p in participants:
                await p2p[p.their.did].stop()

    async def accept_microledger(self, actor: Pairwise, propose: InitRequestLedgerMessage) -> (bool, Microledger):
        transport = await self.transports.spawn(propose.thread_id, actor)
        try:
            # STAGE 1: PROPOSE
            propose.validate()
            await propose.check_signatures(self.crypto, actor.their.did)
            response = InitResponseLedgerMessage()
            response.assign_from(propose)
            await response.add_signature(self.crypto, self.me)
            await transport.switch(response)
        finally:
            await transport.stop()

    async def commit(
            self, ledger: Microledger, transactions: List[Transaction]
    ) -> (bool, List[Transaction]):
        pass

    async def accept_commit(self, actor: Pairwise, ledger: Microledger, transactions: List[Transaction]) -> bool:
        pass
