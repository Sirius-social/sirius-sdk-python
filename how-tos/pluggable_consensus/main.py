import os
import sys
import json
import uuid
import asyncio
from typing import Optional, List

import sirius_sdk
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.messaging import Message

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from consts import *
from helpers import establish_connection, AbstractLedger, InMemoryLedger


LEADER = AGENT1
ACCEPTOR1 = AGENT2
ACCEPTOR2 = AGENT3
ACCEPTOR3 = AGENT4

DID_LEADER = 'Th7MpTaRZVRYnPiabds81Y'
DID_ACCEPTOR1 = 'T8MtAB98aCkgNLtNfQx6WG'
DID_ACCEPTOR2 = 'LnXR1rPnncTPZvRdmJKhJQ'
DID_ACCEPTOR3 = 'PNQm3CwyXbN5e39Rw3dXYx'

TYPE_BFT_CONSENSUS_PROPOSE = 'https://didcomm.org/bft-consensus/1.0/propose'
TYPE_BFT_CONSENSUS_PRE_COMMIT = 'https://didcomm.org/bft-consensus/1.0/pre-commit'
TYPE_BFT_CONSENSUS_COMMIT = 'https://didcomm.org/bft-consensus/1.0/commit'
TYPE_BFT_CONSENSUS_PROBLEM = 'https://didcomm.org/bft-consensus/1.0/problem_report'


def log(message: str):
    print(f'\t{message}')


class BFTPluggableConsensus(AbstractStateMachine):

    def __init__(self, microledger: List[sirius_sdk.Pairwise], dkms: AbstractLedger, *args, **kwargs):
        self.ledger: AbstractLedger = ledger
        self.microledger = microledger
        super().__init__(*args, **kwargs)

    async def propose_and_commit(self, txn: dict) -> bool:
        # Act as transaction Leader
        self.ledger.add_transaction(txn)

        # Stage-1: Propose
        co = sirius_sdk.CoProtocolThreadedTheirs(
            thid='consensus1-txn-' + uuid.uuid4().hex,
            theirs=self.microledger
        )
        results = await co.switch(
            message=Message({
                '@type': TYPE_BFT_CONSENSUS_PROPOSE,
                'txn': txn,
                # According to algorithm Merkle-Proofs used for validation by participants
                'uncommitted_root_hash': self.ledger.uncommitted_root_hash
            })
        )
        unreachable = [pairwise.their.did for pairwise, (ok, _) in results.items() if not ok]
        errored = [pairwise.their.did for pairwise, (ok, msg) in results.items() if ok and msg['@type'] != TYPE_BFT_CONSENSUS_PRE_COMMIT]
        if unreachable or errored:
            # Some error occur. Exit with participants notification
            await co.send(
                message=Message({
                    '@type': TYPE_BFT_CONSENSUS_PROBLEM,
                    'problem-code': 'some-code',
                    'explain': 'Some error occur in participants: ' + ','.join([p.their.did for p in unreachable + errored])
                })
            )
            self.ledger.reset_uncommitted()
            return False
        # Allocate PreCommits. Assumed every participant signed self copy of PreCommit so
        # all others may check consistency among all network
        pre_commits = [msg for _, (_, msg) in results.items()]

        # Stage-2: Pre-Commit
        results = await co.switch(
            message=Message({
                '@type': TYPE_BFT_CONSENSUS_COMMIT,
                'pre_commits': pre_commits,
            })
        )
        unreachable = [pairwise.their.did for pairwise, (ok, _) in results.items() if not ok]
        errored = [pairwise.their.did for pairwise, (ok, msg) in results.items() if
                   ok and msg['@type'] != TYPE_BFT_CONSENSUS_COMMIT]
        # Stage-3: check commits
        if unreachable or errored:
            # Some error occur. Exit with participants notification
            await co.send(
                message=Message({
                    '@type': TYPE_BFT_CONSENSUS_PROBLEM,
                    'problem-code': 'some-code',
                    'explain': 'Some error occur in participants: ' + ','.join(
                        [p.their.did for p in unreachable + errored])
                })
            )
            self.ledger.reset_uncommitted()
            return False
        # Commit to local storage
        self.ledger.commit()
        return True

    async def accept_transaction(self, leader: sirius_sdk.Pairwise, txn_propose: Message) -> bool:
        # Act as transaction acceptor
        self.ledger.add_transaction(txn_propose['txn'])
        assert txn_propose['@type'] == TYPE_BFT_CONSENSUS_PROPOSE

        co = sirius_sdk.CoProtocolThreadedP2P(
            thid=txn_propose['~thread']['thid'],
            to=leader
        )
        # Stage-1: Check local dkms is in consistent state with leader
        if self.ledger.uncommitted_root_hash != txn_propose['uncommitted_root_hash']:
            await co.send(message=Message({
                '@type': TYPE_BFT_CONSENSUS_PROBLEM,
                'problem-code': 'some-code',
                'explain': 'non consistent dkms states'
            }))
            self.ledger.reset_uncommitted()
            return False

        # stage-2: send pre-commit response and wait commits from all participants
        # (assumed in production commits will be signed)
        ok, response = await co.switch(message=Message({
            '@type': TYPE_BFT_CONSENSUS_PRE_COMMIT,
            'uncommitted_root_hash': self.ledger.uncommitted_root_hash
        }))
        if ok:
            assert response['@type'] == TYPE_BFT_CONSENSUS_COMMIT
            pre_commits = response['pre_commits']
            # Here developers may check signatures and consistent
            for pre_commit in pre_commits:
                if pre_commit['uncommitted_root_hash'] != self.ledger.uncommitted_root_hash:
                    await co.send(message=Message({
                        '@type': TYPE_BFT_CONSENSUS_PROBLEM,
                        'problem-code': 'some-code',
                        'explain': 'non consistent dkms states'
                    }))
                    self.ledger.reset_uncommitted()
                    return False
            # Ack commit
            await co.send(message=Message({
                '@type': TYPE_BFT_CONSENSUS_COMMIT,
            }))
            self.ledger.commit()
            return True
        else:
            # Timeout occur or something else
            self.ledger.reset_uncommitted()
            return False


async def acceptor(
        topic: str, context: dict,
        microledger: List[sirius_sdk.Pairwise], dkms: AbstractLedger
):
    async with sirius_sdk.context(**context):
        listener = await sirius_sdk.subscribe()
        log(f'{topic}: start listening...')
        async for event in listener:
            if event.pairwise.their.did in [p.their.did for p in microledger]:
                msg_type = event.message.get('@type', None)
                leader: sirius_sdk.Pairwise = event.pairwise
                if msg_type == TYPE_BFT_CONSENSUS_PROPOSE:
                    log(f'{topic}: start accepting transaction')
                    state_machine = BFTPluggableConsensus(
                        microledger=microledger,
                        ledger=ledger
                    )
                    success = await state_machine.accept_transaction(
                        leader=leader,
                        txn_propose=event.message
                    )
                    if success:
                        log(f'{topic}: !!! transaction was successfully accepted')
                        log(f'{topic}: Ledger size: {ledger.size}')
                        log(f'{topic}: Ledger : [%s]' % ', '.join(str(txn) for txn in ledger.committed_txns))
                    else:
                        log(f'{topic}: !!! transaction was not accepted due to error')
                else:
                    log(f'{topic}: unexpected message type: {msg_type}')
            else:
                log(f'{topic}: ignore requests out of Microledger P2P space')


async def commit(
        topic: str, context: dict, txn: dict,
        microledger: List[sirius_sdk.Pairwise], dkms: AbstractLedger
):
    async with sirius_sdk.context(**context):
        log(f'{topic}: transaction propose')
        state_machine = BFTPluggableConsensus(
            microledger=microledger,
            ledger=ledger
        )
        success = await state_machine.propose_and_commit(txn)
        if success:
            log(f'{topic}: !!! transaction was successfully accepted by All participants')
            log(f'{topic}: Ledger size: {ledger.size}')
            log(f'{topic}: Ledger : [%s]' % ', '.join(str(txn) for txn in ledger.committed_txns))
        else:
            log(f'{topic}: !!! transaction was not accepted due to error')


if __name__ == '__main__':

    # All participants establish Cyber-Security P2P with each other
    # Sirius Name it "Microledger" - established relationships with accepted and acting
    # protocols and algorithms
    print('#1')
    microledger_leader = [
        establish_connection(LEADER, DID_LEADER, ACCEPTOR1, DID_ACCEPTOR1),
        establish_connection(LEADER, DID_LEADER, ACCEPTOR2, DID_ACCEPTOR2),
        establish_connection(LEADER, DID_LEADER, ACCEPTOR3, DID_ACCEPTOR3),
    ]
    microledger_acceptor1 = [
        establish_connection(ACCEPTOR1, DID_ACCEPTOR1, LEADER, DID_LEADER),
        establish_connection(ACCEPTOR1, DID_ACCEPTOR1, ACCEPTOR2, DID_ACCEPTOR2),
        establish_connection(ACCEPTOR1, DID_ACCEPTOR1, ACCEPTOR3, DID_ACCEPTOR3),
    ]
    microledger_acceptor2 = [
        establish_connection(ACCEPTOR2, DID_ACCEPTOR2, LEADER, DID_LEADER),
        establish_connection(ACCEPTOR2, DID_ACCEPTOR2, ACCEPTOR1, DID_ACCEPTOR1),
        establish_connection(ACCEPTOR2, DID_ACCEPTOR2, ACCEPTOR3, DID_ACCEPTOR3),
    ]
    microledger_acceptor3 = [
        establish_connection(ACCEPTOR3, DID_ACCEPTOR3, LEADER, DID_LEADER),
        establish_connection(ACCEPTOR3, DID_ACCEPTOR3, ACCEPTOR1, DID_ACCEPTOR1),
        establish_connection(ACCEPTOR3, DID_ACCEPTOR3, ACCEPTOR2, DID_ACCEPTOR2),
    ]

    print('#2')
    asyncio.ensure_future(acceptor(
        topic='Acceptor[1]', context=ACCEPTOR1,
        microledger=microledger_acceptor1, ledger=InMemoryLedger()
    ))
    asyncio.ensure_future(acceptor(
        topic='Acceptor[2]', context=ACCEPTOR2,
        microledger=microledger_acceptor2, ledger=InMemoryLedger()
    ))
    asyncio.ensure_future(acceptor(
        topic='Acceptor[3]', context=ACCEPTOR3,
        microledger=microledger_acceptor3, ledger=InMemoryLedger()
    ))

    async def run():
        await asyncio.sleep(1)
        my_ledger = InMemoryLedger()
        txn_counter = 0
        while True:
            case = input('\tSelect your case (txn, exit): ')
            await asyncio.sleep(1)
            if case == 'txn':
                txn_counter += 1
                message = input('\tEnter txn message: ')
                await commit(
                    topic='Iam', context=LEADER,
                    txn={
                        'message': message,
                        'seq_no': txn_counter
                    },
                    microledger=microledger_leader,
                    ledger=my_ledger
                )
            elif case == 'exit':
                exit(0)
            else:
                log(f'Unexpected case {case}')


    asyncio.get_event_loop().run_until_complete(run())
