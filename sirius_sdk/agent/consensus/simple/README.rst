==================================
Simple consensus procedure
==================================
******************

- Authors: `Pavel Minenkov <https://github.com/Purik>`_
- Since: 2020/08/01

Summary
===============
Simple Consensus procedure demonstrate how **Sirius SDK** helps to define algorithm to solve BFT problem aside participants (deal contragents)


Motivation
===============
Consensus procedure usually is part of IT infrastructure that builds trust environment and available for developers via special framework (Hyperledger Fabric SDK, Ethereum SDK for exampe). Often consensus is pluggable for enterprise solutions, but when you made choice of consensus procedure, you are forced to agree to selected consensus algorithm logic and outputs. 

`Microledger  <https://decentralized-id.com/hyperledger/hgf-2018/Microledgers-Edgechains-Hardman-HGF/>`_ concept make developer free to select The most convenient BFT algorithm for every business process, served in Microledger context, independently.

Solving problem in same manner we have usefull outcomes:

  - Transactions that transmitted across participants of **Microledgers** are localized in small business process (moving some goods in supply-chain process for example). So, you decrease impact of RPS limitation problem compared to approaches based on global network.
  - You may concentrate business abstractions in your consensus code thanks to **Microledger** nature. Your consensus procedure solve BFT problem on level of business relationships, but not on low-level of IT-infrastructure. 
  - Setup Trust environment across participants through **Merkle-Proof** thanks to immutable transactions logs.


Tutorial
===============
Simple Consensus procedure consists of two blocks:

  - block 1: creating new transactions ledger
  - block 2: accept transaction to existing ledger by all dealers in Microledger environment.


***************
Block 1: Creating new Ledger.
***************
Before starting of serve business process in trust environment via immutable logs in Microledger participants, we should define procedure of establishing new log instance by every dealer. In this step actor initialize transaction log by genesis and make sure all microledger participants received and accept genesis block.

1. Transactions log initialization: actor notify all participants
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
    ]
  }

2. Participant accept new transaction log creation
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
    ]
  }
