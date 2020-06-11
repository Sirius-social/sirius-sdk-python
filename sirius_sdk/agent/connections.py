from typing import List


class Endpoint:

    def __init__(self, address: str, routing_keys: List[str]):
        self.__address = address
        self.__routing_keys = routing_keys

    @property
    def address(self):
        return self.__address

    @property
    def routing_keys(self) -> List[str]:
        return self.__routing_keys