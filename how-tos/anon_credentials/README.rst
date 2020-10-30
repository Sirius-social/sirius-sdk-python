======================================================================
Anon Creds concept implementation with Sirius transaction model
======================================================================
**Self-sovereign identity** (SSI) bring solution for Identity problem, SSI makes identification decentralization.

Modern solutions of identity are hyper centralized. To unchain centralization chains, SSI proposes
to shift point of identity to identity owner in opposite to idea to maintain much identification providers.

.. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/decentralization_identity.png?raw=true
   :height: 300px
   :width: 600px
   :alt: Identity decentralization

To breathe life into this idea **Hyperledger Indy** implements 3 techniques:

1. `Indy Wallet <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0050-wallets>`_:
   private storage that collects all cryptographic keys, cyber-secure relationships, owner credentials.
   Access to wallet has identity owner only thanks to **pass phrase** that used to encode all data in
   the wallet storage and owner only know **pass phrase**. We may draw an analogy with
   Bitcoin wallet: no bank, no any financial org or gov can know you bitcoin wallet balance
   or control currencies movements. Person who is owner of the bitcoin wallet knows **pass phrase** only
   and modern cryptography and network consensus provide ability for wallet owner control his cash.

2. `AnonCreds <https://github.com/hyperledger-archives/indy-crypto/blob/master/libindy-crypto/docs/anoncreds-design.md>`_
   and `DID (decentralized identifiers) <https://www.w3.org/TR/did-core/#dfn-decentralized-identifiers>`_
   is techniques that solve problem *`how owner who has credentials issued and accepted by A may present same
   credentials to B and B may verify that credentials are issued by A to owner he communication with`*

    .. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/anoncreds.jpg?raw=true
       :height: 300px
       :width: 600px
       :alt: Identity decentralization

    useful outcomes:
      - identity owner may generate different DID for different relationships, so he can operate as anonym
      - credential issued by A has cryptographic parts that make possible to validate
        that credential by verifiers (B) in revealed or ZKP manner
      - identity owner has full access to his credentials (via wallet) and make desicion
        does he want present owned credentials fields and how much to present.
      - every verifier (B) has self `Root Of Trust <https://en.wikipedia.org/wiki/Trust_anchor>`_
        avoiding Root center authorities (RCA) which are imposed by PKI technology.
        PKI with root-of-trust as part of it bring much issues in complex relationships.

3. `DKMS <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0051-dkms>`_
   decentralized key management system based on blockchain distributed ledger and maintaining
   by independent participants (like Sovrin network). DKMS acts as independent **arbiter** in
   mechanisms:

   - Check revocations
   - Check DID verkeys
   - Revocate verkeys by DID controllers
   - Write/Read credential definitions and correspondent cryptography data.
   - Revocation registries: check credential was not revocated.
   - Others...

As noticed earlier in `state-machines <https://github.com/Sirius-social/sirius-sdk-python/tree/master/how-tos/distributed_state_machines>`_ doc
**Sirius SDK** provide specific transaction model that reduce program code complexity.

Sirius Team explore much of open-source Indy Agents. All of them ready to product solutions.
But...
There are hundreds and thousands of code lines for each of Anon-Cred feature:

   - `aries rfc feature 0036 <https://github.com/hyperledger/aries-rfcs/tree/master/features/0036-issue-credential>`_
   - `aries rfc feature 0037 <https://github.com/hyperledger/aries-rfcs/tree/master/features/0037-present-proof>`_
   - etc.

Yoc can see below, implementation of prover role (feature 0037 state-machine) takes 35 lines of code:

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


You may check demo source code `here <https://github.com/Sirius-social/sirius-sdk-python/blob/master/how-tos/anon_credentials/main.py>`_