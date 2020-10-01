from abc import ABC, abstractmethod
from inspect import iscoroutinefunction
from typing import List

from sirius_sdk.errors.exceptions import BaseSiriusException
from sirius_sdk.agent.agent import TransportLayers


class AbstractStateMachine(ABC):

    def __init__(self, transports: TransportLayers, time_to_live: int = 60, logger=None, *args, **kwargs):
        """
        :param transports: aries-rfc transports factory
        :param time_to_live: state machine time to live to finish progress
        """
        self.__transports = transports
        self.__time_to_live = time_to_live
        self.__is_aborted = False
        if logger is not None:
            if iscoroutinefunction(logger) or callable(logger):
                pass
            else:
                raise RuntimeError('Expect logger is iscoroutine function or callable object')
        self.__logger = logger

    @property
    def transports(self) -> TransportLayers:
        return self.__transports

    @property
    def time_to_live(self) -> int:
        return self.__time_to_live

    @property
    def is_aborted(self) -> bool:
        return self.__is_aborted

    @property
    @abstractmethod
    def protocols(self) -> List[str]:
        raise NotImplemented('Need to be implemented in descendant')

    async def abort(self):
        """Abort state-machine"""
        self.__is_aborted = True

    async def log(self, **kwargs) -> bool:
        if self.__logger:
            kwargs = dict(**kwargs)
            kwargs['state_machine_id'] = id(self)
            await self.__logger(**kwargs)
        else:
            return False


class StateMachineTerminatedWithError(BaseSiriusException):

    def __init__(self, problem_code: str, explain: str, notify: bool = True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.problem_code = problem_code
        self.explain = explain
        self.notify = notify


class StateMachineAborted(BaseSiriusException):
    pass
