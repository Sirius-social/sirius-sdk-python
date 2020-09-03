==================================
SDK to develop Smart-Contracts in Indy environment
==================================

.. image:: https://raw.githubusercontent.com/Sirius-social/sirius-sdk-python/master/docs/_static/sirius_logo.png
   :height: 64px
   :width: 64px
   :alt: sirius logo


Key Features
============

- Develop state-machines over `Aries protocols <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0003-protocols#aries-rfc-0003-protocols>`_ in blocking develoment style avoiding **Callback Hell**.
- Supports `Aries concepts <https://github.com/hyperledger/aries-rfcs/tree/master/concepts>`_ and `features <https://github.com/hyperledger/aries-rfcs/tree/master/features>`_.
- Make it easy to solve identity problem, tune complex identity task for your demand:

  - Setup `Indy Agent <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0004-agents>`_ in Cloud (Sirius Hub) or deploy self developed one
  - Configure private keys management system on your side: database, **HSM**, `Indy Wallet <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0050-wallets>`_, etc.
  - Configure Trust environment with your contragents via `Microledgers <https://github.com/sovrin-foundation/protocol#the-relationship-agent-plane>`_, `Sovrin Network <https://sovrin.org/>`_, other `Indy Ledgers <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0051-dkms>`_, `Triple Signed Receips <https://opentransactions.org/wiki/Triple-Signed_Receipts>`_ out of box.


Installation
===============
.. code-block:: shell
   :linenos:

   pip install sirius-sdk



