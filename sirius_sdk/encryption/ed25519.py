import json
from typing import Sequence
from collections import OrderedDict

from sirius_sdk.errors.exceptions import SiriusCryptoError
from sirius_sdk.encryption.custom import *


def ensure_is_bytes(b58_or_bytes: Union[str, bytes]) -> bytes:
    if isinstance(b58_or_bytes, str):
        return b58_to_bytes(b58_or_bytes)
    else:
        return b58_or_bytes


def prepare_pack_recipient_keys(
        to_verkeys: Sequence[bytes],
        from_verkey: bytes = None,
        from_sigkey: bytes = None
) -> (str, bytes):
    """
    Assemble the recipients block of a packed message.

    :param to_verkeys: Verkeys of recipients
    :param from_verkey: Sender Verkey needed to authcrypt package
    :param from_sigkey: Sender Sigkey needed to authcrypt package
    :return A tuple of (json result, key)
    """
    if from_verkey is not None and from_sigkey is None or \
            from_sigkey is not None and from_verkey is None:
        raise SiriusCryptoError(
            'Both verkey and sigkey needed to authenticated encrypt message'
        )

    cek = nacl.bindings.crypto_secretstream_xchacha20poly1305_keygen()
    recips = []

    for target_vk in to_verkeys:
        target_pk = nacl.bindings.crypto_sign_ed25519_pk_to_curve25519(
            target_vk
        )
        if from_verkey:
            sender_vk = bytes_to_b58(from_verkey).encode("ascii")
            enc_sender = nacl.bindings.crypto_box_seal(sender_vk, target_pk)
            sk = nacl.bindings.crypto_sign_ed25519_sk_to_curve25519(
                from_sigkey
            )

            nonce = nacl.utils.random(nacl.bindings.crypto_box_NONCEBYTES)
            enc_cek = nacl.bindings.crypto_box(cek, nonce, target_pk, sk)
        else:
            enc_sender = None
            nonce = None
            enc_cek = nacl.bindings.crypto_box_seal(cek, target_pk)

        recips.append(
            OrderedDict(
                [
                    ("encrypted_key", bytes_to_b64(enc_cek, urlsafe=True)),
                    (
                        "header",
                        OrderedDict(
                            [
                                ("kid", bytes_to_b58(target_vk)),
                                (
                                    "sender",
                                    bytes_to_b64(enc_sender, urlsafe=True)
                                    if enc_sender
                                    else None,
                                ),
                                (
                                    "iv",
                                    bytes_to_b64(nonce, urlsafe=True)
                                    if nonce
                                    else None,
                                ),
                            ]
                        ),
                    ),
                ]
            )
        )

    data = OrderedDict(
        [
            ("enc", "xchacha20poly1305_ietf"),
            ("typ", "JWM/1.0"),
            ("alg", "Authcrypt" if from_verkey else "Anoncrypt"),
            ("recipients", recips),
        ]
    )
    return json.dumps(data), cek


def locate_pack_recipient_key(
        recipients: Sequence[dict],
        my_verkey: bytes,
        my_sigkey: bytes
) -> (bytes, str, str):
    """
    Locate pack recipient key.

    Decode the encryption key and sender verification key from a
    corresponding recipient block, if any is defined.

    :param recipients: Recipients to locate
    :param my_verkey: Verkey needed to auth-decrypt
    :param my_sigkey: Sigkey needed to auth-decrypt
    :return A tuple of (cek, sender_vk, recip_vk_b58)

    Raises: ValueError: If no corresponding recipient key found
    """
    not_found = []
    for recip in recipients:
        if not recip or "header" not in recip or "encrypted_key" not in recip:
            raise ValueError("Invalid recipient header")

        recip_vk_b58 = recip["header"].get("kid")

        if bytes_to_b58(my_verkey) != recip_vk_b58:
            not_found.append(recip_vk_b58)
            continue

        pk = nacl.bindings.crypto_sign_ed25519_pk_to_curve25519(my_verkey)
        sk = nacl.bindings.crypto_sign_ed25519_sk_to_curve25519(my_sigkey)

        encrypted_key = b64_to_bytes(recip["encrypted_key"], urlsafe=True)

        if "iv" in recip["header"] and recip["header"]["iv"] and \
                "sender" in recip["header"] and recip["header"]["sender"]:
            nonce = b64_to_bytes(recip["header"]["iv"], urlsafe=True)
            enc_sender = b64_to_bytes(recip["header"]["sender"], urlsafe=True)
        else:
            nonce = None
            enc_sender = None

        if nonce and enc_sender:
            sender_vk = nacl.bindings.crypto_box_seal_open(
                enc_sender,
                pk,
                sk
            ).decode("ascii")
            sender_pk = nacl.bindings.crypto_sign_ed25519_pk_to_curve25519(
                b58_to_bytes(sender_vk)
            )
            cek = nacl.bindings.crypto_box_open(
                encrypted_key,
                nonce,
                sender_pk,
                sk
            )
        else:
            sender_vk = None
            cek = nacl.bindings.crypto_box_seal_open(encrypted_key, pk, sk)
        return cek, sender_vk, recip_vk_b58
    raise ValueError(
        "No corresponding recipient key found in {}".format(not_found)
    )


def encrypt_plaintext(
        message: str, add_data: bytes, key: bytes
) -> (bytes, bytes, bytes):
    """
    Encrypt the payload of a packed message.

    :param message: Message to encrypt
    :param add_data: additional data
    :param key: Key used for encryption
    :return A tuple of (ciphertext, nonce, tag)
    """
    nonce = nacl.utils.random(
        nacl.bindings.crypto_aead_chacha20poly1305_ietf_NPUBBYTES
    )
    message_bin = message.encode("ascii")
    output = nacl.bindings.crypto_aead_chacha20poly1305_ietf_encrypt(
        message_bin, add_data, nonce, key
    )
    mlen = len(message)
    ciphertext = output[:mlen]
    tag = output[mlen:]
    return ciphertext, nonce, tag


def decrypt_plaintext(
        ciphertext: bytes, recips_bin: bytes, nonce: bytes, key: bytes
) -> str:
    """
    Decrypt the payload of a packed message.

    :param ciphertext
    :param recips_bin
    :param nonce
    :param key
    :return The decrypted string
    """
    output = nacl.bindings.crypto_aead_chacha20poly1305_ietf_decrypt(
        ciphertext, recips_bin, nonce, key
    )
    return output.decode("ascii")


def pack_message(
        message: str,
        to_verkeys: Sequence[Union[bytes, str]],
        from_verkey: Union[bytes, str] = None,
        from_sigkey: Union[bytes, str] = None
) -> bytes:
    """
    Assemble a packed message for a set of recipients, optionally including
    the sender.

    :param message: The message to pack
    :param to_verkeys: (Sequence of bytes or base58 string) The verkeys to pack the message for
    :param from_verkey: (bytes or base58 string) The sender verkey
    :param from_sigkey: (bytes or base58 string) The sender sigkey
    :return The encoded message
    """

    to_verkeys = [ensure_is_bytes(vk) for vk in to_verkeys]
    from_verkey = ensure_is_bytes(from_verkey)
    from_sigkey = ensure_is_bytes(from_sigkey)

    recips_json, cek = prepare_pack_recipient_keys(
        to_verkeys,
        from_verkey,
        from_sigkey
    )
    recips_b64 = bytes_to_b64(recips_json.encode("ascii"), urlsafe=True)

    ciphertext, nonce, tag = encrypt_plaintext(
        message,
        recips_b64.encode("ascii"),
        cek
    )

    data = OrderedDict(
        [
            ("protected", recips_b64),
            ("iv", bytes_to_b64(nonce, urlsafe=True)),
            ("ciphertext", bytes_to_b64(ciphertext, urlsafe=True)),
            ("tag", bytes_to_b64(tag, urlsafe=True)),
        ]
    )
    return json.dumps(data).encode("ascii")


def unpack_message(
        enc_message: Union[bytes, dict], my_verkey: Union[bytes, str], my_sigkey: Union[bytes, str]
) -> (str, Optional[str], str):
    """
    Decode a packed message.

    Disassemble and unencrypt a packed message, returning the message content,
    verification key of the sender (if available), and verification key of the
    recipient.

    :param enc_message: The encrypted message
    :param my_verkey: (bytes or base58 string) Verkey for decrypt
    :param my_sigkey: (bytes or base58 string) Sigkey for decrypt
    :return A tuple of (message, sender_vk, recip_vk)
    Raises:
        ValueError: If the packed message is invalid
        ValueError: If the packed message reipients are invalid
        ValueError: If the pack algorithm is unsupported
        ValueError: If the sender's public key was not provided

    """
    my_verkey = ensure_is_bytes(my_verkey)
    my_sigkey = ensure_is_bytes(my_sigkey)

    if not isinstance(enc_message, bytes) and \
            not isinstance(enc_message, dict):
        raise TypeError(
            'Expected bytes or dict, got {}'.format(type(enc_message))
        )
    if isinstance(enc_message, bytes):
        try:
            enc_message = json.loads(enc_message)
        except Exception as err:
            raise ValueError("Invalid packed message") from err

    protected_bin = enc_message["protected"].encode("ascii")
    recips_json = b64_to_bytes(
        enc_message["protected"], urlsafe=True
    ).decode("ascii")
    try:
        recips_outer = json.loads(recips_json)
    except Exception as err:
        raise ValueError("Invalid packed message recipients") from err

    alg = recips_outer["alg"]
    is_authcrypt = alg == "Authcrypt"
    if not is_authcrypt and alg != "Anoncrypt":
        raise ValueError("Unsupported pack algorithm: {}".format(alg))
    cek, sender_vk, recip_vk = locate_pack_recipient_key(
        recips_outer["recipients"], my_verkey, my_sigkey
    )
    if not sender_vk and is_authcrypt:
        raise ValueError(
            "Sender public key not provided for Authcrypt message"
        )

    ciphertext = b64_to_bytes(enc_message["ciphertext"], urlsafe=True)
    nonce = b64_to_bytes(enc_message["iv"], urlsafe=True)
    tag = b64_to_bytes(enc_message["tag"], urlsafe=True)

    payload_bin = ciphertext + tag
    message = decrypt_plaintext(payload_bin, protected_bin, nonce, cek)

    return message, sender_vk, recip_vk
