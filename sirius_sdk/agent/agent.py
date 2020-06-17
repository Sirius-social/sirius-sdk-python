from ..encryption import P2PConnection
from .wallet.wallets import DynamicWallet
from .connections import AgentRPC, AgentEvents


class Agent:

    def __init__(self, server_address: str, credentials: bytes, p2p: P2PConnection):
        self.__server_address = server_address
        self.__credentials = credentials
        self.__p2p = p2p
        self.__rpc = None
        self.__events = None
        self.__wallet = None

    @property
    def wallet(self) -> DynamicWallet:
        return self.__wallet

    async def open(self):
        rpc = AgentRPC.create(self.__server_address, self.__credentials, self.__p2p)
        self.__wallet = DynamicWallet(rpc=rpc)
        self.__rpc = rpc

    async def close(self):
        if self.__rpc:
            await self.__rpc.close()
            self.__wallet = None
