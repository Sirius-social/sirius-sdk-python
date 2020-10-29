======================================================================
Distributed state-machine. Tangible example.
======================================================================
Pictures and examples are borrowed from `Daniel Hardman GitHub page <https://github.com/dhh1128/distributed-state-machine/blob/master/README.md>`_

**Sirius SDK** uses state machine approach to all complexity for relationships digitalization and automation.
Often in practice people are imagining a state machine
at the individual level, but **Sirius** imagine a distributed state machine covering the relationships
network as a whole.


Example
=================
Let's talk about techniques in the abstract. But We also want an easy, tangible example.
So consider this situation. We have a giant spaceship like the ones in Star Wars.
This spaceship is like an aircraft carrier; it contains bunches of smaller, one-man fighters,
and it needs to be able to launch these fighters into combat. The fighters normally sit in a launch bay,
where mechanics can work on them in normal clothes. However, sometimes the launch bay is depressurized,
in which case the only way to enter from inside the larger ship is to pass through an airlock in a
space suit. We have 4 airlocks, A, B, C, and D--and one launch bay door, E. It looks something like this:

.. image:: https://raw.githubusercontent.com/Sirius-social/sirius-sdk-python/master/docs/_static/airlocks.jpg
   :height: 400px
   :width: 640px
   :alt: AirCraft


There are at least interesting two state machine types in this situation:

- The state machine for the bay door E.
- The state machines for the airlocks A, B, C, and D.

You can see that these state machines interact with each other. We don’t want to be able to open
bay door if any of airlock is open so the launch bay will be depressurized. We don’t want to be able to open a
any of airlock if baydoor is open. The airlocks have to coordinate with one another
and with the bay door to achieve consensus on a target state for the launch bay. Furthermore,
there can be a lag in transitions, and timeouts can occur, just like there are timing considerations
in our consensus algorithm.

Now, let’s describe each of the state machines in isolation, formally. State machines consist
of states and transitions. Transitions are triggered by events. Some events are triggered
manually (e.g., someone pushes a button to cycle an airlock); others might be automatic
(e.g., once the bay door finishes opening, the bay door should automatically go into an open state).
A simple way to model state machines is with a matrix, where states are rows, events are columns,
and transitions are the intersections or cells.

How Sirius schedule state-machine
====================================
As noticed above, State machines consist of states and transitions, transitions are triggered by events.
**Sirius SDK** provide mechanisms to provide transition logic in imperative style: line-by-line avoiding handlers and callbacks


In code example below we see BayDoor state-machine that process open command in block-style programming manner
instead of using handlers and callbacks. This approach make code more user friendly.

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

**Sirius SDK** provide it via thread/coroutine suspend-resume. Scheduling mechanism based on
threading/microthreading/coroutines depends on programming languages and it native cooperative
multitasking mechanisms.
Regardless of concrete mechanism, developer may be sure his code is running on separate CPU Stack and
**SDK** scheduler will allocate CPU time when it needed, so your transmition code may be imagine as
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

Communication abstractions are implemented in following classes:

- `CoProtocolP2PAnon <https://github.com/Sirius-social/sirius-sdk-python/blob/538cc33b579d7232a8ef40d47994d2156176c3a5/sirius_sdk/hub/coprotocols.py#L77>`_:
  communicate with participant who does not have Pairwise record. Useful for P2P initialization procedure.
- `CoProtocolP2P <https://github.com/Sirius-social/sirius-sdk-python/blob/538cc33b579d7232a8ef40d47994d2156176c3a5/sirius_sdk/hub/coprotocols.py#L143>`_:
  communicate with participant in P2P context
- `CoProtocolThreadedP2P <https://github.com/Sirius-social/sirius-sdk-python/blob/538cc33b579d7232a8ef40d47994d2156176c3a5/sirius_sdk/hub/coprotocols.py#L207>`_:
  communicate with participant in P2P context marking messages with unique `process-thread-id <https://github.com/hyperledger/aries-rfcs/tree/master/concepts/0008-message-id-and-threading>`_
- `CoProtocolThreadedTheirs <https://github.com/Sirius-social/sirius-sdk-python/blob/538cc33b579d7232a8ef40d47994d2156176c3a5/sirius_sdk/hub/coprotocols.py#L260>`_:
  communicate with group of participants in parallel.

It is available thanks to scheduling mechanism on server-side

.. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/scheduling_state_machines.png?raw=true
   :alt: State machine scheduling
