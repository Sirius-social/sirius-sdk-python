======================================================================
Distributed state-machine. Tangible example.
======================================================================
Pictures and examples are borrowed from `Daniel Hardman GitHub page <https://github.com/dhh1128/distributed-state-machine/blob/master/README.md>`_

**Sirius SDK** uses the state machine approach to tackle all the complexity of relationships digitalization and automation.
It is common to consider a state machine at the individual level, but **Sirius** considers a distributed state machine covering the relationships
network as a whole.


Example
=================
Let's talk about techniques in the abstract. But we also want an easy, tangible example.
So consider the following situation. We have a giant spaceship, like the one in Star Wars.
This spaceship is an aircraft carrier; it contains bunches of smaller, one-man fighters,
and it needs to be able to launch these fighters into combat. The fighters normally sit in a launch bay,
where mechanics can work on them in normal clothes. However, sometimes the launch bay is depressurized,
in which case the only way to enter from inside the larger ship is to pass through an airlock in a
space suit. We have 4 airlocks, A, B, C, and D--and one launch bay door, E. It looks something like this:

.. image:: https://raw.githubusercontent.com/Sirius-social/sirius-sdk-python/master/docs/_static/airlocks.jpg
   :height: 400px
   :width: 640px
   :alt: Space Ship


There are at least two interesting state machine types in this situation:

- The state machine for the bay door E.
- The state machines for the airlocks A, B, C, and D.

You can see that these state machines interact with each other. We don’t want to be able to open
bay door if any of airlock is open so the launch bay will be depressurized. We also don’t want to be able to open
any of airlock if bay door is open. The airlocks have to coordinate with one another
and with the bay door to achieve consensus on a target state for the launch bay. Furthermore,
there can be a lag in transitions, and timeouts can occur, just like there are timing considerations
in our consensus algorithm.

Now, let’s formally describe each state machine separately. State machine consist
of states and transitions. Transitions are triggered by events. Some events are triggered
manually (e.g., someone pushes a button to cycle an airlock); others might be automatic
(e.g., once the bay door finishes opening, the bay door should automatically go into an open state).

How Sirius schedules state-machine
====================================
As noticed above, State machines consist of states and transitions, transitions are triggered by events.
**Sirius SDK** provides mechanisms to utilize the transition logic in imperative style: line-by-line avoiding handlers and callbacks


In the code example below we see BayDoor state-machine that process open command in block-style programming manner
instead of using handlers and callbacks. This approach makes code more user friendly.

.. code-block:: python

     async def open(self) -> bool:
        log('Bay Door: start opening')
        # Detect if Environment is Friendly or No to make decision
        environment = await self.__detect_current_environment()
        if environment == Environment.FRIENDLY:
            await self.__transition_to(State.OPENED)
            log('Bay Door: opening finished successfully')
            return True
        else:
            log('Bay Door: opening finished with error due to non Non-Friendly environment')
            return False

**Sirius SDK** provides it via thread/coroutine suspend-resume. The scheduling mechanism is based on
threading/microthreading/coroutines depends on programming language and its native cooperative
multitasking mechanisms.
Regardless of concrete mechanism, developer may be sure that his code is running on separate CPU Stack and
**SDK** scheduler will allocate CPU time when it needed, so your transition code may be considered as
micro-application that is **turing machine**.

.. code-block:: python

     # SWITCH method suspend runtime thread until participant will respond or error/timeout occur
     ok, response = await communication.switch(
         message=Message({
             '@type': TYPE_STATE_REQUEST
         })
     )

Suspend/Resume context and awaiting responses from participants driven by communication abstractions like in
**GoLang** `concurrency mechanism <https://tour.golang.org/concurrency/2>`_ based on communication channels.
Communication abstractions are closely related to `Aries RFCs CoProtocol abstraction <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0003-protocols>`_.

Communication abstractions are implemented in the following classes:

- `CoProtocolP2PAnon <https://github.com/Sirius-social/sirius-sdk-python/blob/538cc33b579d7232a8ef40d47994d2156176c3a5/sirius_sdk/hub/coprotocols.py#L77>`_:
  communicate with participant who does not have Pairwise record. Useful for P2P initialization procedure
- `CoProtocolP2P <https://github.com/Sirius-social/sirius-sdk-python/blob/538cc33b579d7232a8ef40d47994d2156176c3a5/sirius_sdk/hub/coprotocols.py#L143>`_:
  communicate with participant in P2P context
- `CoProtocolThreadedP2P <https://github.com/Sirius-social/sirius-sdk-python/blob/538cc33b579d7232a8ef40d47994d2156176c3a5/sirius_sdk/hub/coprotocols.py#L207>`_:
  communicate with participant in P2P context marking messages with unique `process-thread-id <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0008-message-id-and-threading>`_
- `CoProtocolThreadedTheirs <https://github.com/Sirius-social/sirius-sdk-python/blob/538cc33b579d7232a8ef40d47994d2156176c3a5/sirius_sdk/hub/coprotocols.py#L260>`_:
  communicate with group of participants in parallel.

It is available thanks to scheduling mechanism on server-side

.. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/scheduling_state_machines.png?raw=true
   :alt: State machine scheduling


Scheduling runtime context via communication abstractions:

.. code-block:: python

     # Communicate with group of participants
     communication = sirius_sdk.CoProtocolThreadedTheirs(
        thid='request-id-' + uuid.uuid4().hex,
        theirs=self.airlocks,
     )
     # SWITCH method suspend runtime thread until events will be accumulated or error occur
     results = await communication.switch(
        message=Message({
            '@type': TYPE_STATE_REQUEST
        })
     )

     ...
     # Communicate with participants in P2P context
     communication = sirius_sdk.CoProtocolThreadedP2P(
        thid='request-id-' + uuid.uuid4().hex,
        to=self.baydoor
     )
     # SWITCH method suspend runtime thread until participant will respond or error/timeout occur
     ok, response = await communication.switch(
        message=Message({
            '@type': TYPE_STATE_REQUEST
        })
     )


Let's connect the dots
====================================
- **Sirius** state-machines are implemented as micro-applications that acts in concurrent environment
  managing by **SDK** scheduler in close relationship with server-side **Hub** scheduler.
- **Transitions** are triggered by **events**. Events are considered as `Aries message types <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0003-protocols#message-types>`_
  ordered and packed in streams that considered as `Co-Protocols <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0003-protocols#what-is-a-protocol>`_

.. image:: https://github.com/hyperledger/aries-rfcs/blob/master/concepts/0003-protocols/co-protocols.png?raw=true
   :height: 100px
   :width: 200px
   :alt: Co-Protocols

- **Messages** that considered as Events have format and structure that was approved by participants
  in consensual or mandatory manner. Such an approach provides maximum dive into business processes automation.
- **Useful output**: Communications entities, BayDoor and AirLocks, may have different hardware and software
  versions, so State-machines in practice will have different implementation but whole distributed state-machine
  will continue to work thanks to **Messages** (events) approved by each part.
- **Sirius SDK** provides **Turing completeness** in its transition model that is similar
  to Google **GoLang** concurrency model. So the developer may control environment for state-machines
  transition steps with much algorithms complexity.

.. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/automata_theory.png?raw=true
   :height: 150px
   :width: 200px
   :alt: Automata theory

- **Sirius SDK** transaction model is based on TCP connection to **Indy agent** with running co-protocols scheduler.
  This solution gives an opportunity to:

  - Implement the same concurrency model (block-style programming for physically asynchronous things)
    for any programming language regardless of concurrency model of the specific language and its tools
  - Reduce development, maintaining, testing costs for complex things

Run sample
======================
You may run `Code sample <https://github.com/Sirius-social/sirius-sdk-python/blob/2715325ca5d6e23f7fd3546094467718d5a844ab/how-tos/distributed_state_machines/main.py#L215>`_
and deep dive into **Sirius SDK**. To avoid Space Ship depressurizing devices state-machine detect
environment kinds named as *friendly* and *hostile*

.. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/airlocks_screen.png?raw=true
   :alt: Sample

As you can see on the screenshot above no one of airlocks can't be opened while Bay Door is open and
Space Ship will not be depressurized. Moreover, the sample code emulates delays in open/close actions.

Conclusions
====================
To deploy the whole distributed state machine to production system we should build test matrix
to check that failures are missing. **Sirius SDK** may help
to do this rapidly thanks to its lightweight micro-applications environment.

Also Self-sovereign identity concept provides atomic building blocks to construct complicated relationships
between independent entities (Humans, Businesses, IoT).
Cryptography support and communication abstractions are out of the box thanks to **Sirius SDK**.
Moreover, the developer can upgrade the existing tools due to the multi-language and open-source nature of the solution.

We will show later why we can't view the presented distributed-state-machine as a consensus procedure for building **Trust**.