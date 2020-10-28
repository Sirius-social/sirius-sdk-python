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

