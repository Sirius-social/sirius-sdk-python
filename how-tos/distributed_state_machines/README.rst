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

