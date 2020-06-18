from ..abstract.anoncreds import AbstractAnonCreds
from ....agent.connections import AgentRPC


class AnonCredsProxy(AbstractAnonCreds):

    def __init__(self, rpc: AgentRPC):
        self.__rpc = rpc