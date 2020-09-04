==================================
Simple consensus procedure
==================================

- Authors: `Pavel Minenkov <https://github.com/Purik>`_, `Talgat Umarbaev <https://github.com/umarbaev>`_, `Igor Fedorov <https://github.com/igorexax3mal>`_
- Since: 2020/08/01

Summary
===============
Simple Consensus procedure demonstrate how **Sirius SDK** helps to define algorithm to solve BFT problem aside participants (deal contragents).
Notice it is algorithm for demo purpose actually and in practice you should use some
kind of production ready approaches: **Tendermint**, **Plenum**, overlap some enterprise framework like **Hyperledger** family through defining Edge-Chain protocol.

Motivation
===============
Consensus procedure usually is part of IT infrastructure that builds trust environment and available for developers via special framework (Hyperledger Sawtooth SDK, Ethereum SDK for exampe). Often consensus is pluggable for enterprise solutions, but when you made choice of consensus procedure, you are forced to agree to selected consensus algorithm logic and outputs in any point of your project.

`Microledger  <https://decentralized-id.com/hyperledger/hgf-2018/Microledgers-Edgechains-Hardman-HGF/>`_ concept make developer free to select The most convenient `BFT <https://www-inst.eecs.berkeley.edu//~cs162/fa12/hand-outs/Original_Byzantine.pdf>`_ algorithm for every business process, served in Microledger context, independently.

Solving problem in same manner we have usefull outcomes:

  - Transactions that transmitted across participants of **Microledgers** are localized in small business process (moving some goods in supply-chain process for example). So, you decrease impact of RPS limitation problem compared to approaches based on global network.
  - You may concentrate business abstractions in your consensus code thanks to **Microledger** nature. Your consensus procedure solve BFT problem on level of business relationships, but not on low-level of IT-infrastructure. 
  - Setup Trust environment across participants through **Merkle-Proof** thanks to immutable transactions logs.


Tutorial
===============

Roles
^^^^^^^^^^^^^^^^^^^^^
There are two roles in this protocol: **Actor** and **Participant(s)**. Actor is participant who initialize process. It is anticipated that all participants has established `pairwise <https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol>`_ connections previously, so they all established `Microledger <https://github.com/hyperledger/aries-rfcs/blob/master/concepts/0051-dkms/dkms-v4.md#43-microledgers>`_.

Threading
^^^^^^^^^^^^^^^^^^^^^
Consensus procedure implemented via declaration of `Edge-Chain protocol <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0003-protocols>`_. It is anticipated that all participants at microledger space use state-machine to progress state, to map protocol message to machine instance it is used `Aries RFCs threading <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0008-message-id-and-threading>`_ concept.

Protocol
^^^^^^^^^^^^^^^^^^^^^
**did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/simple-consensus/1.0/**

Reference
^^^^^^^^^^^^^^^^^^^^^

Simple Consensus procedure covers two use-cases:

  - use-cases 1: creating new transactions ledger
  - use-cases 2: accept transaction to existing ledger by all dealers in Microledger environment.


***************
Use-Case 1: Creating new Ledger.
***************

Before starting of serve business process in trust environment via immutable logs in Microledger participants, we should define procedure of establishing new log instance by every dealer. In this step actor initialize transaction log by genesis and make sure all microledger participants received and accept genesis block.

.. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/create_new_ledger.png?raw=true
   :alt: Create new transactions log


Step-1. Transactions log initialization: actor notify all participants (Send propose)
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

  {
    "@id": "2edc21c7-4111-4fb2-88af-fa8479068a59",
    "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/simple-consensus/1.0/initialize-request",
    "timeout_sec": 60,              # optional
    "ledger": {
        "genesis": [
          {
            ...,
            "txnMetadata": {"seqNo": 2}
          }
        ],
        "name": "Ledger-7b929353ebb1450b979aa336a0338677",
        "root_hash": "3sgNJmsXpmin7P5C6jpHiqYfeWwej5L6uYdYoXTMc1XQ"
    },
    "ledger~hash": {
        "base58": "EcLFhsY7UhBCQoMbKMaAcAYbRCVWbYkNJZ2oSEDsgDvC",
        "func": "sha256"
    },
    "participants": [
        "did:peer:Th7MpTaRZVRYnPiabds81Y",
        "did:peer:T8MtAB98aCkgNLtNfQx6WG"
     ],
     "signatures": [
        {
          "participant": "did:peer:Th7MpTaRZVRYnPiabds81Y",
          "signature": {
            "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/signature/1.0/ed25519Sha512_single",
            "sig_data": "AAAAAF9RXJd7ImZ1bmMiOiAic2hhMjU2Ii...",
            "signature": "ns8Av8kvy1K0mAR08v3flwce9yxyaB0wSjI_dzbpAxiBxSpZ2-YpN-0vifDHMf7yn4c6UC57nv1GFRdo6IQ0Bw==",
            "signer": "FYmoFw55GeQH7SRFa37dkx1d2dZ3zUF8ckg7wmL7ofN4"
           }
        },
        {
          "participant": "did:peer:T8MtAB98aCkgNLtNfQx6WG",
          "signature": {
            "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/signature/1.0/ed25519Sha512_single",
            "sig_data": "AAAAAF9RXJd...",
            "signature": "_Oh48kK9I_QNiBRJfU-_HPAUxyIcrn3Ba8QwspSqiy8AMLMN4h8vbozImSr2dnVS2RaOfimWDgWVtZCTvbdjBQ==",
            "signer": "FEvX3nsJ8VjW4qQv4Dh9E3NDEx1bUPDtc9vkaaoKVyz1"
          }
        }
    ],
    "~thread": {
        "thid": "simple-consensus-machine-98fd8d72-80f6-4419-abc2-c65ea39d0f38",
    }
  }
 

Every time actor needs to initialize new transaction log, it should initialize transactions ledger by genesis block, calc merkle tree root, then notify all dealers in **Microledger** context and make sure all of them initialized self copy of transactions log.

- **timeout_sec**: optiobnal field, set time to live for state machine
- **ledger**: contains genesis block and merkle-proof data
    - **ledger.genesis**: array of transactions that initialize new ledger - genesis block. Notice that **txnMetadata** is reserved attribute that contains ledger-specific data
    - **ledger.name**: unique name of ledger that addresses it univocally.
    - **ledger.root_hash**: root hash of the Merkle-Tree that maps to this ledger
- **ledger~hash**: hash of the ledger
    - **ledger~hash.base58**: base58 presentation of hash bytes for **ledger** field
    - **ledger~hash.func**: hash func that used to calculate hash bytes array
- **participants**: list of dealers who serve transactions. It is assumed all participants established `pairwise <https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol>`_ with each other. It make available to map verkeys for signatures to participants `DIDs <https://www.w3.org/TR/did-core/#dfn-decentralized-identifiers>`_. List of pairwise define Microledger.
- **signatures**: `signatures  <https://github.com/hyperledger/aries-rfcs/tree/master/features/0234-signature-decorator>`_ of ledger~hash for participants. Any microledger participant may check ledger consistency with neighbours.


Step-2. Participant accept new transaction log creation and build signature with self-verkey (pre-commit)
^^^^^^^^^^^^^^^^^^^^^


.. code-block:: python

  {
    "@id": "30140f93-d96c-4a41-8b8f-98587685d07e",
    "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/simple-consensus/1.0/initialize-response",
    "ledger": {
        "genesis": [
          {
            ...
            "txnMetadata": {"seqNo": 1}
          }
        ],
        "name": "Ledger-7b929353ebb1450b979aa336a0338677",
        "root_hash": "3sgNJmsXpmin7P5C6jpHiqYfeWwej5L6uYdYoXTMc1XQ"
    },
    "ledger~hash": {
        "base58": "EcLFhsY7UhBCQoMbKMaAcAYbRCVWbYkNJZ2oSEDsgDvC",
        "func": "sha256"
    },
    "participants": [
        "did:peer:Th7MpTaRZVRYnPiabds81Y",
        "did:peer:T8MtAB98aCkgNLtNfQx6WG"
     ],
     "signatures": [
        {
          "participant": "did:peer:Th7MpTaRZVRYnPiabds81Y",
          "signature": {
            "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/signature/1.0/ed25519Sha512_single",
            "sig_data": "AAAAAF9RXJd7ImZ1bmMiOiAic2hhMjU2Ii...",
            "signature": "ns8Av8kvy1K0mAR08v3flwce9yxyaB0wSjI_dzbpAxiBxSpZ2-YpN-0vifDHMf7yn4c6UC57nv1GFRdo6IQ0Bw==",
            "signer": "FYmoFw55GeQH7SRFa37dkx1d2dZ3zUF8ckg7wmL7ofN4"
           }
        },
        {
          "participant": "did:peer:T8MtAB98aCkgNLtNfQx6WG",
          "signature": {
            "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/signature/1.0/ed25519Sha512_single",
            "sig_data": "AAAAAF9RXJd...",
            "signature": "_Oh48kK9I_QNiBRJfU-_HPAUxyIcrn3Ba8QwspSqiy8AMLMN4h8vbozImSr2dnVS2RaOfimWDgWVtZCTvbdjBQ==",
            "signer": "FEvX3nsJ8VjW4qQv4Dh9E3NDEx1bUPDtc9vkaaoKVyz1"
          }
        }
    ],
    "~thread": {
        "thid": "simple-consensus-machine-98fd8d72-80f6-4419-abc2-c65ea39d0f38",
    }
  }



Step-3. Actor check responses from all participants and check ledger consistency. (commit)
^^^^^^^^^^^^^^^^^^^^^
If there is no problems, actor sends `Ack message  <https://github.com/hyperledger/aries-rfcs/tree/master/features/0015-acks>`_ to all neighbors or `problem-report <https://github.com/hyperledger/aries-rfcs/tree/master/features/0035-report-problem>`_.


***************
Use-Case 2: Accept transaction to existing ledger by all dealers in Microledger environment.
***************
For existing ledger (transactions log) participants may progress business process issuing transactions. Format and rules to build transactions is result of agreement among participants.

.. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/merkle_proof.png?raw=true
   :alt: Merkle-Proofs

Stage-1. Propose transactions block [stage-propose]
^^^^^^^^^^^^^^^^^^^^^
.. code-block:: python

  {
      "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/simple-consensus/1.0/stage-propose",
      "@id": "33a6fd13-0c45-4642-a27d-4315c7455216",
      "participants": [
        "did:peer:T8MtAB98aCkgNLtNfQx6WG",
        "did:peer:LnXR1rPnncTPZvRdmJKhJQ",
        "did:peer:Th7MpTaRZVRYnPiabds81Y"
      ],
      "transactions": [
        {
          ...
          "txnMetadata": {
            "txnTime": "2020-09-04 17:31:18.355738",
            "seqNo": 3
          }
        },
        {
          ...
          "txnMetadata": {
            "txnTime": "2020-09-04 17:31:18.355738",
            "seqNo": 4
          }
        },
        {
          ...
          "txnMetadata": {
            "txnTime": "2020-09-04 17:31:18.355738",
            "seqNo": 5
          }
        }
      ],
      "state": {
        "name": "Ledger-1389425dd0304e898880550d1376cbf8",
        "seq_no": 2,
        "size": 2,
        "uncommitted_size": 5,
        "root_hash": "3sgNJmsXpmin7P5C6jpHiqYfeWwej5L6uYdYoXTMc1XQ",
        "uncommitted_root_hash": "3r79w6pcm7zyX5TfY7eoUdcF7EBsTpBcHGpN7iJfpSmY"
      },
      "hash": "2ff01c13f2bf8f89d077f18c12ceb218",
      "timeout_sec": 60
  }
