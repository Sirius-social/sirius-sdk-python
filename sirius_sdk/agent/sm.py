from abc import ABC, abstractmethod
from typing import List

from sirius_sdk.errors.exceptions import BaseSiriusException
from sirius_sdk.agent.agent import TransportLayers


class AbstractStateMachine(ABC):

    def __init__(self, transports: TransportLayers, time_to_live: int = 60):
        """
        :param transports: aries-rfc transports factory
        :param time_to_live: state machine time to live to finish progress
        """
        self.__transports = transports
        self.__time_to_live = time_to_live

    @property
    def transports(self) -> TransportLayers:
        return self.__transports

    @property
    def time_to_live(self) -> int:
        return self.__time_to_live

    @property
    @abstractmethod
    def protocols(self) -> List[str]:
        raise NotImplemented('Need to be implemented in descendant')


class StateMachineTerminatedWithError(BaseSiriusException):

    def __init__(self, problem_code: str, explain: str, notify: bool = True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.problem_code = problem_code
        self.explain = explain
        self.notify = notify
