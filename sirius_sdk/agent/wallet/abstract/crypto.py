from abc import ABC, abstractmethod
from typing import Optional, Any


class AbstractCrypto(ABC):

    @abstractmethod
    async def create_key(self, seed: str=None, crypto_type: str=None) -> str:
        """
        Creates keys pair and stores in the wallet.

        :param seed: string, (optional) Seed that allows deterministic key creation (if not set random one will be
                        created). Can be UTF-8, base64 or hex string.
        :param crypto_type: string, // Optional (if not set then ed25519 curve is used);
                        Currently only 'ed25519' value is supported for this field.

        :return: verkey: Ver key of generated key pair, also used as key identifier
        """
        raise NotImplemented()

    @abstractmethod
    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        """
        Saves/replaces the meta information for the giving key in the wallet.

        :param verkey: the key (verkey, key id) to store metadata.
        :param metadata: the meta information that will be store with the key.
        """
        raise NotImplemented()

    @abstractmethod
    async def get_key_metadata(self, verkey: str) -> Optional[dict]:
        """
        Retrieves the meta information for the giving key in the wallet.

        :param verkey: The key (verkey, key id) to retrieve metadata.
        :return: metadata: The meta information stored with the key; Can be null if no metadata was saved for this key.
        """
        raise NotImplemented()

    @abstractmethod
    async def crypto_sign(self, signer_vk: str, msg: bytes) -> bytes:
        """
        Signs a message with a key.

        Note to use DID keys with this function you can call indy_key_for_did to get key id (verkey) for specific DID.

        :param signer_vk:  id (verkey) of my key. The key must be created by calling create_key or create_and_store_my_did
        :param msg: a message to be signed
        :return: a signature string
        """
        raise NotImplemented()

    @abstractmethod
    async def crypto_verify(self, signer_vk: str, msg: bytes, signature: bytes) -> bool:
        """
        Verify a signature with a verkey.

        Note to use DID keys with this function you can call key_for_did to get key id (verkey) for specific DID.

        :param signer_vk: verkey of signer of the message
        :param msg: message that has been signed
        :param signature: a signature to be verified
        :return: valid: true - if signature is valid, false - otherwise
        """
        raise NotImplemented()

    @abstractmethod
    async def anon_crypt(self, recipient_vk: str, msg: bytes) -> bytes:
        """
        Encrypts a message by anonymous-encryption scheme.

        Sealed boxes are designed to anonymously send messages to a Recipient given its public key.
        Only the Recipient can decrypt these messages, using its private key.
        While the Recipient can verify the integrity of the message, it cannot verify the identity of the Sender.

        Note to use DID keys with this function you can call key_for_did to get key id (verkey)
        for specific DID.

        Note: use pack_message function for A2A goals.

        :param recipient_vk: verkey of message recipient
        :param msg: a message to be signed
        :return: an encrypted message as an array of bytes
        """
        raise NotImplemented()

    @abstractmethod
    async def anon_decrypt(self, recipient_vk: str, encrypted_msg: bytes) -> bytes:
        """
        Decrypts a message by anonymous-encryption scheme.

        Sealed boxes are designed to anonymously send messages to a Recipient given its public key.
        Only the Recipient can decrypt these messages, using its private key.
        While the Recipient can verify the integrity of the message, it cannot verify the identity of the Sender.

        Note to use DID keys with this function you can call key_for_did to get key id (verkey)
        for specific DID.

        Note: use unpack_message function for A2A goals.

        :param recipient_vk: id (verkey) of my key. The key must be created by calling indy_create_key or create_and_store_my_did
        :param encrypted_msg: encrypted message
        :return: decrypted message as an array of bytes
        """
        raise NotImplemented()

    @abstractmethod
    async def pack_message(self, message: Any, recipient_verkeys: list, sender_verkey: str=None) -> bytes:
        """
        Packs a message by encrypting the message and serializes it in a JWE-like format (Experimental)

        Note to use DID keys with this function you can call did.key_for_did to get key id (verkey)
        for specific DID.

        :param message: the message being sent as a string. If it's JSON formatted it should be converted to a string
        :param recipient_verkeys: a list of Strings which are recipient verkeys
        :param sender_verkey: the sender's verkey as a string. -> When None is passed in this parameter, anoncrypt mode is used
        :returns an Agent Wire Message format as a byte array.
        """
        raise NotImplemented()

    @abstractmethod
    async def unpack_message(self, jwe: bytes) -> dict:
        """
        Unpacks a JWE-like formatted message outputted by pack_message (Experimental)

        #Returns:
        (Authcrypt mode)

        {
            "message": <decrypted message>,
            "recipient_verkey": <recipient verkey used to decrypt>,
            "sender_verkey": <sender verkey used to encrypt>
        }

        (Anoncrypt mode)

        {
            "message": <decrypted message>,
            "recipient_verkey": <recipient verkey used to decrypt>,
        }
        """
        raise NotImplemented()
