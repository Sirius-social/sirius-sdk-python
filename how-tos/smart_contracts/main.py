import os
import sys
import json
import uuid
import random
import asyncio
from abc import abstractmethod
from typing import Optional, List, Dict

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
ACTION_ORDER_DELIVERED = 'action_delivery_successfully'
MARKET_CONN_KEY = '4S5T45AXL9WbfQfvCzSsd25Fkeg8HFm2Hv8ujs4DCsHx'


class BaseSmartContract:

    def __init__(self, microledger: List[sirius_sdk.Pairwise], storage: AbstractMicroledgerList):
        # Setup smart-contract environment
        self.microledger = microledger
        self.me = None
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

    async def process_connection_request(self, request: sirius_sdk.aries_rfc.ConnRequest, actor: sirius_sdk.Pairwise):
        pass

    async def process_text_message(self, request: sirius_sdk.aries_rfc.Message, p2p: sirius_sdk.Pairwise):
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
                    asyncio.ensure_future(self.process_connection_request(event.message, event.pairwise))
                elif isinstance(event.message, sirius_sdk.aries_rfc.Message):
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
                        log(f'{self.caption}: new transactions to ledger [{propose.state.name}] was successfully '
                            f'committed')
                        # Process new transactions
                        for txn in propose.transactions:
                            await self.process_new_transaction(
                                track_id=propose.state.name,
                                transaction=txn,
                                actor=event.pairwise
                            )
                    else:
                        log(f'{self.caption}: new transactions to ledger [{propose.state.name}] commit ERROR!!!')
                        if consensus.problem_report:
                            log(f'{self.caption}: problem-report')
                            log(json.dumps(consensus.problem_report, indent=2, sort_keys=True))


class MarketplaceSmartContract(BaseSmartContract):

    def __init__(self, microledger: List[sirius_sdk.Pairwise], storage: AbstractMicroledgerList):
        super().__init__(microledger, storage)
        self.me = sirius_sdk.Pairwise.Me(did=DID_MARKET, verkey=VERKEY_MARKET)
        self.track_counter = 1
        self.tracks: Dict[str, sirius_sdk.Pairwise] = {}

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
        p2p = self.tracks.get(track_id, None)
        order_delivery_confirmed = False
        if p2p:
            txt_msg = None
            if actor.their.did == DID_FARMER:
                txt_msg = sirius_sdk.aries_rfc.Message(content=f'Order [{track_id}] processed by Farmer')
            elif actor.their.did == DID_DEPOT:
                txt_msg = sirius_sdk.aries_rfc.Message(content=f'Order [{track_id}] processed by Depot')
            elif actor.their.did == DID_DELIVERY:
                txt_msg = sirius_sdk.aries_rfc.Message(content=f'Order [{track_id}] processed by Delivery')
                yes = 'Yes'
                no = 'No'
                ask = sirius_sdk.aries_rfc.Question(
                    valid_responses=[yes, no],
                    question_text=f'{p2p.their.label}, did you received order [{track_id}]',
                    question_detail='Confirm your order is delivered and you do not have issues!',
                    locale='en'
                )
                ask.set_ttl(15)  # Set timeout for answer
                success, answer = await sirius_sdk.aries_rfc.ask_and_wait_answer(
                    query=ask,
                    to=p2p
                )
                if success and answer.response == yes:
                    order_delivery_confirmed = True
            if txt_msg:
                await sirius_sdk.send_to(txt_msg, p2p)
            if order_delivery_confirmed:
                await sirius_sdk.send_to(
                    sirius_sdk.aries_rfc.Message(content=f'Order [{track_id}] delivery confirmed. Welcome again'), p2p
                )
                del self.tracks[track_id]

    async def process_connection_request(self, request: sirius_sdk.aries_rfc.ConnRequest, actor: sirius_sdk.Pairwise):
        async with sirius_sdk.context(**self.agent_conn):
            if actor is not None:
                log(f'{self.caption}: update p2p connection for {actor.their.label}')
            else:
                log(f'{self.caption}: establish new p2p connection')
            endpoints = await sirius_sdk.endpoints()
            my_endpoint = [e for e in endpoints if e.routing_keys == []][0]
            feature_0160 = sirius_sdk.aries_rfc.Inviter(
                me=self.me,
                connection_key=MARKET_CONN_KEY,
                my_endpoint=my_endpoint,
            )
            success, p2p = await feature_0160.create_connection(request)
            if success:
                await sirius_sdk.PairwiseList.ensure_exists(p2p)
                log(f'{self.caption}: pairwise established successfully')
                log(json.dumps(p2p.metadata, indent=2, sort_keys=True))
                # Involve Customer to digital services
                await self.run_virtual_assistant(p2p)
            else:
                log(f'{self.caption}: error while establish P2P connection')
                if feature_0160.problem_report:
                    log('problem report')
                    log(json.dumps(feature_0160.problem_report, indent=2, sort_keys=True))

    async def process_text_message(self, request: sirius_sdk.aries_rfc.Message, p2p: sirius_sdk.Pairwise):
        await self.run_virtual_assistant(p2p)

    async def run_virtual_assistant(self, p2p: sirius_sdk.Pairwise):
        """Virtual assistant support"""
        async with sirius_sdk.context(**self.agent_conn):
            service1 = '!!!Buy!!!'
            service2 = 'Decline'
            log(f'{self.caption} propose digital services to {p2p.their.label}')
            ask = sirius_sdk.aries_rfc.Question(
                valid_responses=[service1, service2],
                question_text=f'{p2p.their.label} welcome to Marketplace',
                question_detail='We are glad to make personal offer for you!',
                locale='en'
            )
            ask.set_ttl(60)  # Set timeout for answer
            success, answer = await sirius_sdk.aries_rfc.ask_and_wait_answer(
                query=ask,
                to=p2p
            )
            if success:
                log(f'{self.caption}: providing service: {answer.response}')
                if answer.response == service1:
                    track_id = f'Track_{self.track_counter}'
                    self.track_counter += 1
                    ok = await self.create_track_id(
                        track_id=track_id,
                        genesis=[
                            # Set responsibility to Farmer
                            Transaction({'action': ACTION_FOR_FARMER})
                        ]
                    )
                    if ok:
                        txt_msg = sirius_sdk.aries_rfc.Message(content=f'Your Order track id: {track_id}', locale='en')
                        # Map Track ID to Customer for notifying
                        self.tracks[track_id] = p2p
                    else:
                        txt_msg = sirius_sdk.aries_rfc.Message(content=f'Something wrong. Try again later', locale='en')
                    await sirius_sdk.send_to(txt_msg, p2p)

    async def create_track_id(self, track_id: str, genesis: List[Transaction]) -> bool:
        """MarketPlace may create new goods track-id"""
        async with sirius_sdk.context(
                **self.agent_conn,
                # Dependency injection for Ledger storage (in-memory, file, database, etc)
                microledgers=self.storage
        ):
            log(f'{self.caption}: propose new track-id: {track_id} ...')
            consensus = simple_consensus.MicroLedgerSimpleConsensus(self.me, time_to_live=15)
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
        self.me = sirius_sdk.Pairwise.Me(did=DID_FARMER, verkey=VERKEY_FARMER)

    @property
    def caption(self) -> str:
        return 'Farm'

    @property
    def agent_conn(self) -> dict:
        return FARMER

    async def process_new_transaction(self, track_id: str, transaction: Transaction, actor: sirius_sdk.Pairwise):
        if transaction.get('action', None) == ACTION_FOR_FARMER:
            log('................................................')
            log(f'{self.caption}: Start processing [{track_id}]')
            await asyncio.sleep(10 + random.randint(3, 10))
            log(f'{self.caption}: Stop processing [{track_id}]')
            log('................................................')
            log(f'{self.caption}: call to DEPOT to move goods with track-id [{track_id}] out...')
            ok = await self.propose_transactions(
                track_id=track_id,
                transactions=[Transaction(
                    {'action': ACTION_FOR_DEPOT}
                )]
            )
            log(f'{self.caption}: OK: {ok}')


class DepotSmartContract(BaseSmartContract):

    def __init__(self, microledger: List[sirius_sdk.Pairwise], storage: AbstractMicroledgerList):
        super().__init__(microledger, storage)
        self.me = sirius_sdk.Pairwise.Me(did=DID_DEPOT, verkey=VERKEY_DEPOT)

    @property
    def caption(self) -> str:
        return 'Depot'

    @property
    def agent_conn(self) -> dict:
        return DEPOT

    async def process_new_transaction(self, track_id: str, transaction: Transaction, actor: sirius_sdk.Pairwise):
        if transaction.get('action', None) == ACTION_FOR_DEPOT:
            log('................................................')
            log(f'{self.caption}: Start processing [{track_id}]')
            await asyncio.sleep(5 + random.randint(1, 5))
            log(f'{self.caption}: Stop processing [{track_id}]')
            log('................................................')
            log(f'{self.caption}: call to Deliverer to move goods with track-id [{track_id}] out...')
            ok = await self.propose_transactions(
                track_id=track_id,
                transactions=[Transaction(
                    {'action': ACTION_FOR_DELIVERER}
                )]
            )
            log(f'{self.caption}: OK: {ok}')


class DelivererSmartContract(BaseSmartContract):

    def __init__(self, microledger: List[sirius_sdk.Pairwise], storage: AbstractMicroledgerList):
        super().__init__(microledger, storage)
        self.me = sirius_sdk.Pairwise.Me(did=DID_DELIVERY, verkey=VERKEY_DELIVERY)

    @property
    def caption(self) -> str:
        return 'Deliverer'

    @property
    def agent_conn(self) -> dict:
        return DELIVERY

    async def process_new_transaction(self, track_id: str, transaction: Transaction, actor: sirius_sdk.Pairwise):
        if transaction.get('action', None) == ACTION_FOR_DELIVERER:
            log('................................................')
            log(f'{self.caption}: Start processing [{track_id}]')
            await asyncio.sleep(10 + random.randint(3, 10))
            log(f'{self.caption}: Stop processing [{track_id}]')
            log('................................................')
            log(f'{self.caption}: Write to Distributed Ledger track-id [{track_id}] order is delivered')
            ok = await self.propose_transactions(
                track_id=track_id,
                transactions=[Transaction(
                    {'action': ACTION_ORDER_DELIVERED}
                )]
            )
            log(f'{self.caption}: OK: {ok}')


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
        while True:
            await asyncio.sleep(10000)

    asyncio.get_event_loop().run_until_complete(run())

