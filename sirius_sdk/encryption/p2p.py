import json
from typing import Tuple, Union

from sirius_sdk.errors.exceptions import SiriusCryptoError
from sirius_sdk.encryption import pack_message, unpack_message


class P2PConnection:
    """"
    Pairwise static connection compatible with Indy SDK
    """

    def __init__(self, my_keys: Tuple[str, str], their_verkey: str):
        """
        :param my_keys: (verkey, sigkey) for encrypt/decrypt operations
        :param their_verkey: verkey of the counterparty
        """
        self.__my_keys = my_keys
        self.__their_verkey = their_verkey

    @property
    def my_verkey(self):
        return self.__my_keys[0]

    @property
    def their_verkey(self):
        return self.__their_verkey

    def pack(self, message: dict) -> bytes:
        """
        Encrypt message

        :param message:
        :return: encrypted message
        """
        packed = pack_message(
            message=json.dumps(message),
            to_verkeys=[self.__their_verkey],
            from_verkey=self.__my_keys[0],
            from_sigkey=self.__my_keys[1]
        )
        return packed

    def unpack(self, enc_message: Union[bytes, dict]) -> dict:
        """
        Decrypt message

        :param enc_message: encoded message
        :return: decrypted message
        """
        try:
            message, sender_vk, recip_vk = unpack_message(
                enc_message=enc_message,
                my_verkey=self.__my_keys[0],
                my_sigkey=self.__my_keys[1]
            )
        except ValueError as e:
            raise SiriusCryptoError(str(e))
        except KeyError as e:
            raise SiriusCryptoError(str(e))
        else:
            return json.loads(message)
