from abc import ABC, abstractmethod
from typing import Optional, List, Any


class AbstractPairwise(ABC):

    @abstractmethod
    async def is_pairwise_exists(self, their_did: str) -> bool:
        """
        Check if pairwise is exists.

        :param their_did: encoded Did.
        :return: true - if pairwise is exists, false - otherwise
        """
        raise NotImplemented

    @abstractmethod
    async def create_pairwise(self, their_did: str, my_did: str, metadata: dict=None, tags: dict=None) -> None:
        """
        Creates pairwise.

        :param their_did: encrypting DID
        :param my_did: encrypting DID
        :param metadata: (Optional) extra information for pairwise
        :param tags: tags for searching operations
        :return: Error code
        """
        raise NotImplemented

    @abstractmethod
    async def list_pairwise(self) -> List[Any]:
        """
        Get list of saved pairwise.

        :return: pairwise_list: list of saved pairwise
        """
        raise NotImplemented

    @abstractmethod
    async def get_pairwise(self, their_did: str) -> Optional[dict]:
        """
        Gets pairwise information for specific their_did.

        :param their_did: encoded Did
        :return: pairwise_info_json: did info associated with their did
        """
        raise NotImplemented

    @abstractmethod
    async def set_pairwise_metadata(self, their_did: str, metadata: dict=None, tags: dict=None) -> None:
        """
        Save some data in the Wallet for pairwise associated with Did.

        :param their_did: encoded DID
        :param metadata: some extra information for pairwise
        :param tags: tags for searching operation
        """
        raise NotImplemented

    @abstractmethod
    async def search(self, tags: dict, limit: int = None) -> (List[dict], int):
        """Search Pairwises

        :param tags: tags based query
        :param limit: max items count
        :return: Results, TotalCount
        """
        raise NotImplemented
