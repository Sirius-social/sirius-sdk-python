from ..encryption import P2PConnection
from .connections import AgentRPC, AgentEvents


class Agent:

    def __init__(self, server_address: str, credentials: bytes, p2p: P2PConnection):
        self.__server_address = server_address
        self.__credentials = credentials
        self.__p2p = p2p
        self.__rpc = None
        self.__events = None

    async def open(self):
        self.__rpc = AgentRPC.create(self.__server_address, self.__credentials, self.__p2p)
        

    async def close(self):
        if self.__rpc:
            await self.__rpc.close()
