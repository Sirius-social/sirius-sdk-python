==================================
Setup developer environment
==================================

It is a complex task to build a trusted environment. Sirius provides separation to the server side and client side.

Server side named **HUB** has the following components:

  - **Endpoint**: address of the server that processes income requests from the Internet - external world
  - **Router**: gives an ability to manipulate with routing keys and forwarding messages to actual Agent instances
  - **Load balancer**: balances income packed message streams among Agent instances.
    Hub User may keep multiple Agent instances since Sirius initialize **Hyperledger Indy**
    with Postgres storage engine support, so Sirius can balance income request stream
    among Postgres replicas.

    - Kafka: balances income packed messages among agent instances
    - Redis: Sirius uses Redis channels to schedule co-protocols (sender+recipient verkeys / thread-id / etc.)
    - Co-protocols scheduler: routes extracted co-protocol stream to correspondent state-machine (managed via SDK on client-side)

  - **SDK**: schedules state-machines on client-side avoiding callback Hell and saves developer from communication "magic"

.. image:: https://raw.githubusercontent.com/Sirius-social/sirius-sdk-python/master/docs/_static/high_level_arch.png
   :height: 640px
   :width: 640px
   :alt: sirius hub


Step-by-step
======================

**Step-1** SDK user should configure development environment:

.. code-block:: python

      import sirius_sdk
      .....

      sirius_sdk.init(
         server_uri="<Sirius Hub URL>",
         credentials="<Hub account credentials>",
         p2p=sirius_sdk.P2PConnection(
           my_keys=("<sdk-public-key>", "<sdk-secret-key>"),
           their_verkey="<agent-side-public-key>"
         )
      )


Required configuration parameters
  - **server_uri**: address of server side to connect client side via SDK
  - **credentials**: encoded information that server use to schedule resources to correspondent Kafka topics
  - **p2p**: Sirius Hub can't access to **SDK-To-Agent** communication stream semantic, it schedule
    and route it to correspondent Kafka topics. Agent that was run on Sirius HUB infrastructure may
    contain hardcoded P2P encryption keys to safely communicate with client side so there is no
    broke points in the trusted environment between SDK user and his Agent.
    User may setup Sirius Hub locally on its own infrastructure. In this case user may avoid p2p encryption between SDK and Agent.


**Step-2** You may call Sirius SDK features

  - Example 1: Check connection to Agent

    .. code-block:: python

          is_connected = await sirius_sdk.ping()
          assert is_connected

  - Example 2: List all my DIDs with metadata

    .. code-block:: python

          my_did = await sirius_sdk.DID.list_my_dids_with_meta()
          print('DID list')
          print(json.dumps(my_did, indent=2))


Code samples
======================
See code samples for DEMO Sirius Hub `here <https://github.com/Sirius-social/sirius-sdk-python/blob/master/how-tos/setup_environment/main.py>`_