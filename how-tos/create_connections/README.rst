======================================================================
Establish security relationships with modern cryptography approaches
======================================================================
Trust environment is a broad concept. Often in present days many blockchain platforms say that
trust environment is immutable storages. But it is restricted view of things. Sirius SDK give flexible tool
to configure Trust with deep dive to your business processes, habits, existing IT approaches.
This is the main reason why Sirius SDK is distributed in multiple programming languages.

As noticed Nick Szabo in `Smart Contracts: Building Blocks for Digital Markets <http://www.truevaluemetrics.org/DBpdfs/BlockChain/Nick-Szabo-Smart-Contracts-Building-Blocks-for-Digital-Markets-1996-14591.pdf>`_
trust environment is not immutable storage only, building blocks of trust are:

- 1. First of these is observability, the ability of the principals to observe each others'
     performance of the contract
- 2. Second objective verifiability, the ability of a principal to prove to an arbitrator
     that a contract has been performed or breached, or the ability of the arbitrator to find this
     out by other means
- 3. Third objective of contract design is privity, the principle that knowledge and control
     over the contents and performance of a contract should be distributed among parties only
     as much as is necessary for the performance of that contract
- 4. Fourth objective is enforceability, and at the same time minimizing the need for enforcement.
     Improved verifiability often also helps meet this fourth objective.
     Reputation, built-in incentives, "self-enforcing" protocols,
     and verifiability can all play a strong part in meeting the fourth objective.
     Computer and network security also can contribute greatly to making smart contracts self-enforcing.

Off course immutable storages that presented by **DLT** and other **blockchain** solutions may solve
this issues. But any tech approach keep in yourself restrictions and potential problems.

Evidence this kind of view:

  **Ethereum co-founder Vitalik Buterin (2018 interview)**

  *“The problem with the current blockchain is this idea that every computer has to verify every transaction,”*
  *If we can move to networks where every computer on average verifies only a small portion of transactions then it can be done better*

  *Blockchains…are a far less efficient computer and database than technologies that have existed for over forty years… efficiency is not what blockchains are built for*

  **Arthur Gervais (founder of Liquidity.Network), June 2018**

  *Let’s say you and I, we are happy to do some transactions with each other.
  We don’t really need to use the blockchain unless we disagree with each other…
  Why would you need the mediator if you are actually in accordance…?*


Instead of enforce tech approaches and architecture, **Sirius SDK** provides *"building blocks"* for configuring
trust environment with maximum response to your demands.

Business environment requires relationships. Trust requires this relationships must be cyber-security.
============================================================================================================================================
Sirius SDK give ability to establish connection relationships in two manners:

- Statically
- Dynamically: with some protocols. Sirius uses `Aries protocols <https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol>`_
  by default but you may use other solutions thanks to **Sirius SDK** is open source

Below we present source code examples.

Case-1: establish connection statically
*************************
Sirius based on **Self-sovereign identity** concept as source point for any relationships to
moving relationships from real world to digital space

