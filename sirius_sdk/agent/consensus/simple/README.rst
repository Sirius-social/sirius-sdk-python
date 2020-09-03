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

