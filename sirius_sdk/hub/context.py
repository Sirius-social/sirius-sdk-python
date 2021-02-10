import asyncio
import logging
import sys
from collections import ChainMap
from copy import deepcopy
from functools import partial

PY37 = sys.version_info >= (3, 7)

if PY37:
    def asyncio_current_task(loop=None):
        """Return the current task or None."""
        try:
            return asyncio.current_task(loop)
        except RuntimeError:
            # simulate old behaviour
            return None
else:
    asyncio_current_task = asyncio.Task.current_task


NO_LOOP_EXCEPTION_MSG = "No event loop found, key {} couldn't be set"


def dict_context_factory(parent_context=None, copy_context=False):
    """A traditional ``dict`` context to keep things simple"""
    if parent_context is None:
        # initial context
        return {}
    else:
        # inherit context
        new_context = parent_context
        if copy_context:
            new_context = deepcopy(new_context)
        return new_context


def ensure_context_exists(task):
    try:
        context = task.context
    except AttributeError:
        context = None

    task.context = dict_context_factory(context)


def get(key, default=None):
    """
    Retrieves the value stored in key from the Task.context dict. If key does not exist,
    or there is no event loop running, default will be returned

    :param key: identifier for accessing the context dict.
    :param default: None by default, returned in case key is not found.
    :return: Value stored inside the dict[key].
    """
    current_task = asyncio_current_task()
    if not current_task:
        raise ValueError(NO_LOOP_EXCEPTION_MSG.format(key))

    ensure_context_exists(current_task)

    return current_task.context.get(key, default)


def set(key, value):
    """
    Sets the given value inside Task.context[key]. If the key does not exist it creates it.

    :param key: identifier for accessing the context dict.
    :param value: value to store inside context[key].
    :raises
    """
    current_task = asyncio_current_task()
    if not current_task:
        raise ValueError(NO_LOOP_EXCEPTION_MSG.format(key))

    ensure_context_exists(current_task)

    current_task.context[key] = value


def clear():
    """
    Clear the Task.context.

    :raises ValueError: if no current task.
    """
    current_task = asyncio_current_task()
    if not current_task:
        raise ValueError("No event loop found")

    ensure_context_exists(current_task)

    current_task.context.clear()
