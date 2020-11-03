import os
import sys
import json
import uuid
import asyncio
from abc import abstractmethod
from typing import Optional, List

import sirius_sdk
from sirius_sdk.messaging import Message
from sirius_sdk.base import AbstractStateMachine, StateMachineTerminatedWithError
from sirius_sdk.agent.microledgers import Transaction
from sirius_sdk.agent.consensus import simple as simple_consensus
from sirius_sdk.agent.microledgers import AbstractMicroledgerList

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from consts import *
from helpers import establish_connection
from ledger import InMemoryLedger, InMemoryLedgerList


def log(message: str):
    print(f'\t{message}')


MARKET = AGENT1
FARMER = AGENT2
DEPOT = AGENT3
DELIVERY = AGENT4

DID_MARKET = 'Th7MpTaRZVRYnPiabds81Y'
VERKEY_MARKET = 'FYmoFw55GeQH7SRFa37dkx1d2dZ3zUF8ckg7wmL7ofN4'
DID_FARMER = 'T8MtAB98aCkgNLtNfQx6WG'
VERKEY_FARMER = 'FEvX3nsJ8VjW4qQv4Dh9E3NDEx1bUPDtc9vkaaoKVyz1'
DID_DEPOT = 'LnXR1rPnncTPZvRdmJKhJQ'
VERKEY_DEPOT = 'BnSWTUQmdYCewSGFrRUhT6LmKdcCcSzRGqWXMPnEP168'
DID_DELIVERY = 'PNQm3CwyXbN5e39Rw3dXYx'
VERKEY_DELIVERY = 'DC8gEkb1cb4T9n3FcZghTkSp1cGJaZjhsPdxitcu6LUj'

ACTION_FOR_FARMER = 'action_farmer'
ACTION_FOR_DEPOT = 'action_for_depot'
ACTION_FOR_DELIVERER = 'action_for_deliverer'
MARKET_CONN_KEY = '4S5T45AXL9WbfQfvCzSsd25Fkeg8HFm2Hv8ujs4DCsHx'


class BaseSmartContract:

    def __init__(self, microledger: List[sirius_sdk.Pairwise], storage: AbstractMicroledgerList):
        # Setup smart-contract environment
        self.microledger = microledger
        self.me = sirius_sdk.Pairwise.Me(did=DID_MARKET, verkey=VERKEY_MARKET)
        self.storage = storage
        self.participants = [p.their.did for p in microledger] + [DID_MARKET]

    @property
    @abstractmethod
    def caption(self) -> str:
        raise NotImplemented

    @property
    @abstractmethod
    def agent_conn(self) -> dict:
        raise NotImplemented

    @abstractmethod
    async def process_new_transaction(self, track_id: str, transaction: Transaction, actor: sirius_sdk.Pairwise):
        """Descendant should implement self reaction to new transaction"""
        raise NotImplemented

    async def process_connection_request(self, request: sirius_sdk.aries_rfc.ConnRequest):
        pass

    async def process_text_message(self, request: Message, p2p: sirius_sdk.Pairwise):
        pass

    async def propose_transactions(self, track_id: str, transactions: List[Transaction]) -> bool:
        async with sirius_sdk.context(
                **self.agent_conn,
                # Dependency injection for Ledger storage (in-memory, file, database, etc)
                microledgers=self.storage
        ):
            log(f'{self.caption}: propose new transactions to track-id: {track_id} ...')
            consensus = simple_consensus.MicroLedgerSimpleConsensus(self.me)
            ledger = await sirius_sdk.Microledgers.ledger(track_id)
            ok, txns = await consensus.commit(
                ledger=ledger,
                participants=self.participants,
                transactions=transactions
            )
            if ok:
                log(f'{self.caption}: propose new transactions to track-id: [{track_id}] was successfully accepted'
                    f'root_hash: {ledger.root_hash}')
            else:
                log(f'{self.caption}: propose new transactions to track-id: [{track_id}] terminated with ERROR!!!')
                if consensus.problem_report:
                    log(f'{self.caption}: problem-report')
                    log(json.dumps(consensus.problem_report, indent=2, sort_keys=True))
            return ok

    async def run(self):
        async with sirius_sdk.context(
                **self.agent_conn,
                # Dependency injection for Ledger storage (in-memory, file, database, etc)
                microledgers=self.storage
        ):
            listener = await sirius_sdk.subscribe()
            log(f'{self.caption}: start listening...')
            # Implement reactive nature of the Smart-Contract
            async for event in listener:
                if isinstance(event.message, sirius_sdk.aries_rfc.ConnRequest):
                    # Process request for new P2P relationship
                    # (run in async thread)
                    asyncio.ensure_future(self.process_connection_request(event.message))
                elif isinstance(event.message, Message):
                    if event.pairwise is not None:
                        # Process Text message
                        # (run in async thread)
                        asyncio.ensure_future(self.process_text_message(event.message, event.pairwise))
                elif isinstance(event.message, simple_consensus.messages.InitRequestLedgerMessage):
                    # Process request for creation new goods Track blockchain ledger
                    log(f'{self.caption}: received request for new tracking of goods')
                    consensus = simple_consensus.MicroLedgerSimpleConsensus(self.me)
                    propose: simple_consensus.messages.InitRequestLedgerMessage = event.message
                    log(f'{self.caption}: start to create new ledger [{propose.ledger["name"]}] for tracking...')
                    ok, ledger = await consensus.accept_microledger(
                        leader=event.pairwise,
                        propose=propose
                    )
                    if ok:
                        log(f'{self.caption}: ledger [{ledger.name}] was created, root_hash: {ledger.root_hash}')
                        transactions = await ledger.get_all_transactions()
                        # Process new transactions
                        for txn in transactions:
                            await self.process_new_transaction(
                                track_id=ledger.name,
                                transaction=txn,
                                actor=event.pairwise
                            )
                    else:
                        log(f'{self.caption}: ledger [{propose.ledger["name"]}] creation ERROR!!!')
                        if consensus.problem_report:
                            log(f'{self.caption}: problem-report')
                            log(json.dumps(consensus.problem_report, indent=2, sort_keys=True))
                elif isinstance(event.message, simple_consensus.messages.ProposeTransactionsMessage):
                    # Process request for new transaction
                    consensus = simple_consensus.MicroLedgerSimpleConsensus(self.me)
                    propose: simple_consensus.messages.ProposeTransactionsMessage = event.message
                    ok = await consensus.accept_commit(
                        leader=event.pairwise,
                        propose=propose
                    )
                    if ok:
                        log(f'{self.caption}: new transactions to ledger [{propose.ledger["name"]}] was successfully '
                            f'committed, root_hash: {ledger.root_hash}')
                        # Process new transactions
                        for txn in propose.transactions:
                            await self.process_new_transaction(
                                track_id=ledger.name,
                                transaction=txn,
                                actor=event.pairwise
                            )
                    else:
                        log(f'{self.caption}: new transactions to ledger [{propose.ledger["name"]}] commit ERROR!!!')
                        if consensus.problem_report:
                            log(f'{self.caption}: problem-report')
                            log(json.dumps(consensus.problem_report, indent=2, sort_keys=True))


class MarketplaceSmartContract(BaseSmartContract):

    def __init__(self, microledger: List[sirius_sdk.Pairwise], storage: AbstractMicroledgerList):
        super().__init__(microledger, storage)

    async def generate_invite_qr(self) -> str:
        async with sirius_sdk.context(**self.agent_conn):
            try:
                connection_key = await sirius_sdk.Crypto.create_key(seed='0000000000000000MARKETPLACE_CONN')
            except sirius_sdk.indy_exceptions.WalletItemAlreadyExists:
                log(f'{self.caption}: conn key {MARKET_CONN_KEY} already exists')
            else:
                log(f'{self.caption}: conn key {connection_key} was created')
                assert connection_key == MARKET_CONN_KEY
            endpoints = await sirius_sdk.endpoints()
            simple_endpoint = [e for e in endpoints if e.routing_keys == []][0]
            market_invitation = sirius_sdk.aries_rfc.Invitation(
                label='MarketPlace',
                recipient_keys=[MARKET_CONN_KEY],
                endpoint=simple_endpoint.address,
                did=DID_MARKET
            )
            log(f'{self.caption}: invitation')
            log(json.dumps(market_invitation, indent=2, sort_keys=True))

            qr_url = await sirius_sdk.generate_qr_code(market_invitation.invitation_url)
            print('MARKET QR URL: ' + qr_url)
            return qr_url

    @property
    def caption(self) -> str:
        return 'MarketPace'

    @property
    def agent_conn(self) -> dict:
        return MARKET

    async def process_new_transaction(self, track_id: str, transaction: Transaction, actor: sirius_sdk.Pairwise):
        # log(f'{self.caption}: new transaction')
        pass

    async def create_track_id(self, track_id: str, genesis: List[Transaction]) -> bool:
        """MarketPlace may create new goods track-id"""
        async with sirius_sdk.context(
                **self.agent_conn,
                # Dependency injection for Ledger storage (in-memory, file, database, etc)
                microledgers=self.storage
        ):
            log(f'{self.caption}: propose new track-id: {track_id} ...')
            consensus = simple_consensus.MicroLedgerSimpleConsensus(self.me)
            ok, ledger = await consensus.init_microledger(
                ledger_name=track_id,
                participants=self.participants,
                genesis=genesis
            )
            if ok:
                log(f'{self.caption}: propose for new track-id: [{track_id}] was successfully accepted by All participants'
                    f'root_hash: {ledger.root_hash}')
            else:
                log(f'{self.caption}: propose for new track-id: [{track_id}] terminated with ERROR!!!')
                if consensus.problem_report:
                    log(f'{self.caption}: problem-report')
                    log(json.dumps(consensus.problem_report, indent=2, sort_keys=True))
            return ok


class FarmSmartContract(BaseSmartContract):

    def __init__(self, microledger: List[sirius_sdk.Pairwise], storage: AbstractMicroledgerList):
        super().__init__(microledger, storage)

    @property
    def caption(self) -> str:
        return 'Farm'

    @property
    def agent_conn(self) -> dict:
        return FARMER

    async def process_new_transaction(self, track_id: str, transaction: Transaction, actor: sirius_sdk.Pairwise):
        # log(f'{self.caption}: new transaction')
        pass


class DepotSmartContract(BaseSmartContract):

    def __init__(self, microledger: List[sirius_sdk.Pairwise], storage: AbstractMicroledgerList):
        super().__init__(microledger, storage)

    @property
    def caption(self) -> str:
        return 'Depot'

    @property
    def agent_conn(self) -> dict:
        return DEPOT

    async def process_new_transaction(self, track_id: str, transaction: Transaction, actor: sirius_sdk.Pairwise):
        # log(f'{self.caption}: new transaction')
        pass


class DelivererSmartContract(BaseSmartContract):

    def __init__(self, microledger: List[sirius_sdk.Pairwise], storage: AbstractMicroledgerList):
        super().__init__(microledger, storage)

    @property
    def caption(self) -> str:
        return 'Deliverer'

    @property
    def agent_conn(self) -> dict:
        return DELIVERY

    async def process_new_transaction(self, track_id: str, transaction: Transaction, actor: sirius_sdk.Pairwise):
        # log(f'{self.caption}: new transaction')
        pass


if __name__ == '__main__':

    # All participants establish Cyber-Security P2P with each other
    # Sirius Name it "Microledger" - established relationships with accepted and acting
    # protocols and algorithms
    print('#1')
    # Microledgers groups of supply-chain
    microledgers = {
        'marketplace': [
            establish_connection(MARKET, DID_MARKET, FARMER, DID_FARMER),
            establish_connection(MARKET, DID_MARKET, DEPOT, DID_DEPOT),
            establish_connection(MARKET, DID_MARKET, DELIVERY, DID_DELIVERY),
        ],
        'farmer': [
            establish_connection(FARMER, DID_FARMER, MARKET, DID_MARKET),
            establish_connection(FARMER, DID_FARMER, DEPOT, DID_DEPOT),
            establish_connection(FARMER, DID_FARMER, DELIVERY, DID_DELIVERY)
        ],
        'depot': [
            establish_connection(DEPOT, DID_DEPOT, MARKET, DID_MARKET),
            establish_connection(DEPOT, DID_DEPOT, FARMER, DID_FARMER),
            establish_connection(DEPOT, DID_DEPOT, DELIVERY, DID_DELIVERY)
        ],
        'deliverer': [
            establish_connection(DELIVERY, DID_DELIVERY, MARKET, DID_MARKET),
            establish_connection(DELIVERY, DID_DELIVERY, FARMER, DID_FARMER),
            establish_connection(DELIVERY, DID_DELIVERY, DEPOT, DID_DEPOT)
        ]
    }
    print('#2')
    # Run smart-contract for Marketplace side
    marketplace = MarketplaceSmartContract(microledger=microledgers['marketplace'], storage=InMemoryLedgerList())
    asyncio.ensure_future(marketplace.generate_invite_qr())
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(1000))

    asyncio.ensure_future(marketplace.run())
    # Run Farmer smart-contract
    farmer = FarmSmartContract(microledger=microledgers['farmer'], storage=InMemoryLedgerList())
    asyncio.ensure_future(farmer.run())
    # Run depot smart-contract
    depot = DepotSmartContract(microledger=microledgers['depot'], storage=InMemoryLedgerList())
    asyncio.ensure_future(depot.run())
    # Run deliverer smart-contract
    deliverer = DelivererSmartContract(microledger=microledgers['deliverer'], storage=InMemoryLedgerList())
    asyncio.ensure_future(deliverer.run())

    async def run():
        await asyncio.sleep(10000)


    asyncio.get_event_loop().run_until_complete(run())

