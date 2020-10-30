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