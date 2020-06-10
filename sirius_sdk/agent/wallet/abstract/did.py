from abc import ABC, abstractmethod
from typing import Optional, List, Any


class AbstractDID(ABC):

    @abstractmethod
    async def create_and_store_my_did(self, did: str=None, seed: str=None, cid: bool=None) -> (str, str):
        """
        Creates keys (signing and encryption keys) for a new
        DID (owned by the caller of the library).
        Identity's DID must be either explicitly provided, or taken as the first 16 bit of verkey.
        Saves the Identity DID with keys in a secured Wallet, so that it can be used to sign
        and encrypt transactions.

        :param did: string, (optional)
                    if not provided and cid param is false then the first 16 bit of the verkey will be
                    used as a new DID;
                    if not provided and cid is true then the full verkey will be used as a new DID;
                    if provided, then keys will be replaced - key rotation use case)
        :param seed: string, (optional) Seed that allows deterministic key creation
                    (if not set random one will be created).
                    Can be UTF-8, base64 or hex string.
        :param cid: bool, (optional; if not set then false is used;)

        :return: DID and verkey (for verification of signature)
        """
        raise NotImplemented

    @abstractmethod
    async def store_their_did(self, did: str, verkey: str=None) -> None:
        """
        Saves their DID for a pairwise connection in a secured Wallet,
        so that it can be used to verify transaction.
        Updates DID associated verkey in case DID already exists in the Wallet.

        :param did: string, (required)
        :param verkey: string (optional, if only pk is provided),
        :return: None
        """
        raise NotImplemented

    @abstractmethod
    async def set_did_metadata(self, did: str, metadata: dict = None) -> None:
        """
        Saves/replaces the meta information for the giving DID in the wallet.

        :param did: the DID to store metadata.
        :param metadata: the meta information that will be store with the DID.
        :return: Error code
        """
        raise NotImplemented

    @abstractmethod
    async def list_my_dids_with_meta(self) -> List[Any]:
        """
        List DIDs and metadata stored in the wallet.

        :return: List of DIDs with verkeys and meta data.
        """
        raise NotImplemented

    @abstractmethod
    async def get_did_metadata(self, did) -> Optional[dict]:
        """
        Retrieves the meta information for the giving DID in the wallet.

        :param did: The DID to retrieve metadata.
        :return: metadata: The meta information stored with the DID; Can be null if no metadata was saved for this DID.
        """
        raise NotImplemented

    @abstractmethod
    async def key_for_local_did(self, did: str) -> str:
        """
        Returns ver key (key id) for the given DID.

        "key_for_local_did" call looks data stored in the local wallet only and skips freshness checking.

        Note if you want to get fresh data from the ledger you can use "key_for_did" call
        instead.

        Note that "create_and_store_my_did" makes similar wallet record as "create_key".
        As result we can use returned ver key in all generic crypto and messaging functions.

        :param did: The DID to resolve key.
        :return: key: The DIDs ver key (key id).
        """
        raise NotImplemented

    @abstractmethod
    async def key_for_did(self, pool_name: str, did: str) -> str:
        """
        Returns ver key (key id) for the given DID.

        "key_for_did" call follow the idea that we resolve information about their DID from
        the ledger with cache in the local wallet. The "open_wallet" call has freshness parameter
        that is used for checking the freshness of cached pool value.

        Note if you don't want to resolve their DID info from the ledger you can use
        "key_for_local_did" call instead that will look only to local wallet and skip
        freshness checking.

        Note that "create_and_store_my_did" makes similar wallet record as "create_key".
        As result we can use returned ver key in all generic crypto and messaging functions.

        :param pool_name: Pool Name.
        :param did: The DID to resolve key.
        :return: key:   The DIDs ver key (key id).
        """
        raise NotImplemented

    @abstractmethod
    async def create_key(self, seed: str=None) -> str:
        """
        Creates keys pair and stores in the wallet.

        :param seed: string, (optional) Seed that allows deterministic key creation
                    (if not set random one will be created).
                    Can be UTF-8, base64 or hex string.
        :return: verkey: Ver key of generated key pair, also used as key identifier
        """
        raise NotImplemented

    @abstractmethod
    async def replace_keys_start(self, did: str, seed: str=None) -> str:
        """
        Generated new keys (signing and encryption keys) for an existing
        DID (owned by the caller of the library).

        :param did: signing DID
        :param seed: string, (optional) Seed that allows deterministic key creation
                    (if not set random one will be created). Can be UTF-8, base64 or hex string.
        :return: verkey
        """
        raise NotImplemented

    @abstractmethod
    async def replace_keys_apply(self, did: str) -> None:
        """
        Apply temporary keys as main for an existing DID (owned by the caller of the library).

        :param did: The DID to resolve key.
        :return: Error code
        """
        raise NotImplemented

    @abstractmethod
    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        """
        Creates keys pair and stores in the wallet.

        :param verkey: the key (verkey, key id) to store metadata.
        :param metadata: the meta information that will be store with the key.
        :return: Error code
        """
        raise NotImplemented

    @abstractmethod
    async def get_key_metadata(self, verkey: str) -> dict:
        """
        Retrieves the meta information for the giving key in the wallet.

        :param verkey: The key (verkey, key id) to retrieve metadata.
        :return: metadata: The meta information stored with the key; Can be null if no metadata was saved for this key.
        """
        raise NotImplemented

    @abstractmethod
    async def set_endpoint_for_did(self, did: str, address: str, transport_key: str) -> None:
        """
        Set/replaces endpoint information for the given DID.

        :param did: The DID to resolve endpoint.
        :param address: The DIDs endpoint address.
        :param transport_key: The DIDs transport key (ver key, key id).
        :return: Error code
        """
        raise NotImplemented

    @abstractmethod
    async def get_endpoint_for_did(self, pool_name: str, did: str) -> (str, Optional[str]):
        """
        Returns endpoint information for the given DID.

        :param pool_name: Pool name.
        :param did: The DID to resolve endpoint.
        :return: (endpoint, transport_vk)
        """
        raise NotImplemented

    @abstractmethod
    async def get_my_did_with_meta(self, did: str) -> Any:
        """
        Get DID metadata and verkey stored in the wallet.

        :param did: The DID to retrieve metadata.
        :return: DID with verkey and metadata.
        """
        raise NotImplemented

    @abstractmethod
    async def abbreviate_verkey(self, did: str, full_verkey: str) -> str:
        """
        Retrieves abbreviated verkey if it is possible otherwise return full verkey.

        :param did: The DID.
        :param full_verkey: The DIDs verification key,
        :return: metadata: Either abbreviated or full verkey.
        """
        raise NotImplemented

    @abstractmethod
    async def qualify_did(self, did: str, method: str) -> str:
        """
        Update DID stored in the wallet to make fully qualified, or to do other DID maintenance.
            - If the DID has no prefix, a prefix will be appended (prepend did:peer to a legacy did)
            - If the DID has a prefix, a prefix will be updated (migrate did:peer to did:peer-new)

        Update DID related entities stored in the wallet.

        :param did: target DID stored in the wallet.
        :param method: method to apply to the DID.
        :return: fully qualified did
        """
        raise NotImplemented
