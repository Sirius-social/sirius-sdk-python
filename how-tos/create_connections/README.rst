======================================================================
Establish security relationships with modern cryptography approaches
======================================================================
Trust environment is a broad concept. Often in present days many blockchain platforms say that
trust environment is immutable storages. But it is restricted view of things. Sirius SDK give flexible tool
to configure Trust with deep dive to your business processes, habits, existing IT approaches.
This is the main reason why Sirius SDK is distributed in multiple programming languages.

As noticed Nick Szabo in `Smart Contracts: Building Blocks for Digital Markets <http://www.truevaluemetrics.org/DBpdfs/BlockChain/Nick-Szabo-Smart-Contracts-Building-Blocks-for-Digital-Markets-1996-14591.pdf>`_
trust environment is not immutable storage only, building blocks of trust are:

1. First of these is observability, the ability of the principals to observe each others'
     performance of the contract
2. Second objective verifiability, the ability of a principal to prove to an arbitrator
     that a contract has been performed or breached, or the ability of the arbitrator to find this
     out by other means
3. Third objective of contract design is privity, the principle that knowledge and control
     over the contents and performance of a contract should be distributed among parties only
     as much as is necessary for the performance of that contract
4. Fourth objective is enforceability, and at the same time minimizing the need for enforcement.
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
*******************************************
Sirius based on **Self-sovereign identity** concept as source point to start
moving relationships from real world to digital space.

.. image:: https://raw.githubusercontent.com/Sirius-social/sirius-sdk-python/master/docs/_static/ssi_actor.png
   :height: 200px
   :width: 250px
   :alt: Actor

So to statically add new relationship you must keep:

- **DID**: `Decentralized identifier <https://www.w3.org/TR/did-core/#dfn-decentralized-identifiers>`_
- **Verkey**: public key that used to verify digital signatures presented by `DID Controller <https://www.w3.org/TR/did-core/#dfn-did-controllers>`_
- **Endpoint**: Reachable internet address to communicate with

.. code-block:: python

      # You received necessity data
      their_did, their_verkey, their_endpoint = ...
      .....
      # You may generate DID, Verkey on self side to establish P2P connection
      # But in advanced, you may use public static DID if you are public organization or any business
      # Sirius does not enforce your choice
      my_did, my_verkey = await sirius_sdk.DID.create_and_store_my_did()
      connection = sirius_sdk.Pairwise(
            me=sirius_sdk.Pairwise.Me(my_did, my_verkey),
            their=sirius_sdk.Pairwise.Their(their_did, 'My static connection', their_endpoint, their_verkey)
      )
      await sirius_sdk.PairwiseList.create(connection)


Case-2: establish connection dynamically
*******************************************
In practice we should to have more flexible procedure to establish connection.
For example, Connection initiator (Inviter) can generate information packet, include all data for establishing
connection with him and store some context in his Invitation: web page session, for example.
**Sirius**, by default, has implementation for `Aries protocols <https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol>`_
for this purposes. But you may adapt this logic and configure for yourself or extend thanks to
**Sirius SDK** is open source.


1. Inviter build connection:

.. code-block:: python

      # Inviter create invitation and publish it for example on Web page via QR code
      # or send via Email
      # Connection key may be used to determine connection context: business-process, web-session, etc.
      invitation = sirius_sdk.aries_rfc.Invitation(
          label='Inviter', endpoint=endpoint.address, recipient_keys=[connection_key]
      )
      qr_code_content = invitation.invitation_url


2. Invitee received invitation, for example he was scanned QR code

.. code-block:: python

    invitation = sirius_sdk.aries_rfc.Invitation.from_url(qr_code_content)
    ...
    # Allocate new did for new connection (you may use const public DID)
    did, verkey = await sirius_sdk.DID.create_and_store_my_did()
    my_endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0]
    # Allocate and configure state-machine
    state_machine = sirius_sdk.aries_rfc.Invitee(
        me=sirius_sdk.Pairwise.Me(did, verkey),
        my_endpoint=my_endpoint
    )
    # Run state-machine that process Aries 0160 protocol
    ok, pairwise = await state_machine.create_connection(invitation=invitation, my_label='Invitee')
    assert ok is True


3. Inviter received connection-request

.. code-block:: python

      listener = await sirius_sdk.subscribe()
      # Listen events from Endpoints
      async for event in listener:
          # Implementation for Reactive nature of your business-logic
          request = event.message
          if isinstance(request, sirius_sdk.aries_rfc.ConnRequest):
              # Allocate new DID,Verkey for new connection (you may use const public DID)
              did, verkey = await sirius_sdk.DID.create_and_store_my_did()
              endpoint = [e for e in await sirius_sdk.endpoints() if e.routing_keys == []][0]
              state_machine = sirius_sdk.aries_rfc.Inviter(
                  me=sirius_sdk.Pairwise.Me(did, verkey),
                  connection_key=event.recipient_verkey,  # You may detect use-cases by connection-key value
                  my_endpoint=endpoint
              )
              ok, pairwise = await state_machine.create_connection(request)
              assert ok is True



Code samples
*******************************************

1. `Both cases <https://github.com/Sirius-social/sirius-sdk-python/blob/master/how-tos/create_connections/create_connection.py>`_
2. `Statically <https://github.com/Sirius-social/sirius-sdk-python/blob/223b9591e795f0bfe48ee3ec6a537ecedc9f65e4/how-tos/create_connections/create_connection.py#L101>`_
3. `Dynamically <https://github.com/Sirius-social/sirius-sdk-python/blob/223b9591e795f0bfe48ee3ec6a537ecedc9f65e4/how-tos/create_connections/create_connection.py#L118>`_