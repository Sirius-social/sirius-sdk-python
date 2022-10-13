======================================================================
Anon Creds concept implementation with Sirius transaction model
======================================================================
**Self-sovereign identity** (SSI) brings the solution to the Identity problem, SSI makes identification decentralized.

Modern identity solutions are hyper centralized. To unchain the centralization chains, SSI proposes
to shift the point of identity to the identity owner in opposite to the idea of maintaining many identification providers.

.. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/decentralization_identity.png?raw=true
   :height: 300px
   :width: 600px
   :alt: Identity decentralization

To breathe life into this idea **Hyperledger Indy** implements 3 techniques:

1. `Indy Wallet <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0050-wallets>`_:
   a private storage that collects all cryptographic keys, cyber-secure relationships, owner credentials.
   Only the identity owner has access to the wallet thanks to the **pass phrase** that is used to encode all data in
   the wallet storage and only owner knows this **pass phrase**. We may draw an analogy with
   Bitcoin wallet: no bank, no any financial organization or government can know you bitcoin wallet balance
   or control currency movements. Only the person who is the owner of the bitcoin wallet knows the **pass phrase**
   and modern cryptography and network consensus algorithms provide an ability for wallet owner to control his cash.

2. `AnonCreds <https://github.com/hyperledger-archives/indy-crypto/blob/master/libindy-crypto/docs/anoncreds-design.md>`_
   and `DID (decentralized identifiers) <https://www.w3.org/TR/did-core/#dfn-decentralized-identifiers>`_
   are the techniques that solve *`how the owner who has credentials issued and accepted by A may present 
   these credentials to B and B may verify that the credentials are issued by A to the owner he communicates with`*

    .. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/anoncreds.jpg?raw=true
       :height: 300px
       :width: 600px
       :alt: Identity decentralization

    Useful outcomes:
      - identity owner may generate different DIDs for different relationships, so he can operate as anonym
      - credential issued by A has cryptographic parts that make it possible to validate
        that credential by verifiers (B) in revealed or ZKP manner
      - identity owner has full access to his credentials (via wallet) and decides whether to provide its own credential 
      fields and to what extent.
      - every verifier (B) has its own `Root Of Trust <https://en.wikipedia.org/wiki/Trust_anchor>`_
        avoiding Root center authorities (RCA) which are imposed by PKI technology.
        PKI with root-of-trust as a part of it brings many issues in complex relationships.

3. `DKMS <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0051-dkms>`_
   decentralized key management system is based on blockchain distributed dkms and maintained
   by independent participants (like Sovrin network). DKMS acts as independent **arbiter** in the following
   mechanisms:

   - Check revocations
   - Check DID verkeys
   - Revocate verkeys by DID controllers
   - Write/Read credential definitions and correspondent cryptography data.
   - Revocation registries: check if credential was not revocated.
   - Others...

As it noticed earlier in `state-machines <https://github.com/Sirius-social/sirius-sdk-python/tree/master/how-tos/distributed_state_machines>`_ doc,
**Sirius SDK** provides a specific transaction model that reduce the program code complexity.

**Sirius** Team explores much of open-source Indy Agents. All of them are ready to product solutions.
But...
There are hundreds and thousands of code lines for each of Anon-Cred feature:

   - `aries rfc feature 0036 <https://github.com/hyperledger/aries-rfcs/tree/master/features/0036-issue-credential>`_
   - `aries rfc feature 0037 <https://github.com/hyperledger/aries-rfcs/tree/master/features/0037-present-proof>`_
   - etc.

One can see below that the implementation of the prover role (feature 0037 state-machine) takes 35 lines of code:

.. image:: https://github.com/hyperledger/aries-rfcs/raw/master/features/0037-present-proof/credential-presentation.png
       :height: 200px
       :width: 300px
       :alt: Prover role

source code `link <https://github.com/Sirius-social/sirius-sdk-python/blob/b7ef83a6c955429245b450d17a67e8a1a8ec48b0/sirius_sdk/agent/aries_rfc/feature_0037_present_proof/state_machines.py#L222>`_

.. code-block:: python

    offer_msg = offer
    try:
        offer_msg.validate()
    except SiriusValidationError as e:
        raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, e.message)

    # Step-1: Process Issuer Offer
    cred_request, cred_metadata = await sirius_sdk.AnonCreds.prover_create_credential_req(
        prover_did=self.__issuer.me.did,
        cred_offer=offer_msg.offer,
        cred_def=offer_msg.cred_def,
        master_secret_id=master_secret_id
    )

    # Step-2: Send request to Issuer
    request_msg = RequestCredentialMessage(
        comment=comment,
        locale=locale,
        cred_request=cred_request,
        doc_uri=doc_uri
    )

    # Switch to await participant action
    resp = await self.switch(request_msg)
    if not isinstance(resp, IssueCredentialMessage):
        raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, 'Unexpected @type: %s' % str(resp.type))

    issue_msg = resp
    try:
        issue_msg.validate()
    except SiriusValidationError as e:
        raise StateMachineTerminatedWithError(REQUEST_NOT_ACCEPTED, e.message)

    # Step-3: Store credential
    cred_id = await self._store_credential(
        cred_metadata, issue_msg.cred, offer.cred_def, None, issue_msg.cred_id
    )
    ack = Ack(
        thread_id=issue_msg.ack_message_id if issue_msg.please_ack else issue_msg.id,
        status=Status.OK,
        doc_uri=doc_uri
    )
    await self.send(ack)

DEMO
=================
You may check demo source code `here <https://github.com/Sirius-social/sirius-sdk-python/blob/master/how-tos/anon_credentials/main.py>`_

Let's pay attention to some lines of code
==========================================

1. DKMS is maintaining independently of DIDs. Indy Wallet uses **Elliptic Curve Cryptography** inside
   so all relationships and anon-cred mechanisms acts in virtual mathematics world of elliptic curves
   and wallet is only a secure storage that supports reusing its relationships using the persistent wallet storage.

    .. code-block:: python

        # You may select what DKMS network you should work with (Sovrin, IndicioNet, etc.)
        dkms = await sirius_sdk.dkms(network_name)


2. **Sirius SDK** wraps Indy credential mechanism tools to Native object-oriented-mechanisms. Thanks
   to open-source nature of the SDK developer may upgrade declarations to his demands

   .. code-block:: python

        # Ensure schema exists on DKMS
        schema_ = await dkms.ensure_schema_exists(anon_schema, ISSUER_DID)
        # Ensure CredDefs is stored to DKMS
        cred_def_fetched = await dkms.fetch_cred_defs(tag='TAG', schema_id=schema_.id)

3. **Sirius SDK** combines Object-Oriented (OOP) developing and Procedure-Oriented developing (POP)
   style. POP is powerful for the communication part of use-cases algorithms with many entities that have active nature,
   OOP is powerful for manipulating objects with passive nature: storages, entities, etc.
   Developer may combine them both to reach maximum productivity and rationality.

   .. code-block:: python

        dkms = await sirius_sdk.dkms(network_name)
        feature_0037 = sirius_sdk.aries_rfc.Verifier(
            prover=prover,
            dkms=dkms
        )
        success = await feature_0037.verify(proof_request)

