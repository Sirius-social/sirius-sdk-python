r"""https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
"""
import re
import time
import json
import struct
import base64
from typing import List, Optional, Any

from ....errors.exceptions import *
from ....messaging import Message
from ....agent.wallet.wallets import DynamicWallet
from ..base import AriesProtocolMessage, AriesProtocolMeta


class ConnProtocolMessage(AriesProtocolMessage, metaclass=AriesProtocolMeta):
    """Aries feature 0160 Message implementation

    https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
    """

    PROTOCOL = 'connection'

    @staticmethod
    async def sign_field(wallet: DynamicWallet, field_value: Any, my_verkey: str) -> dict:
        timestamp_bytes = struct.pack(">Q", int(time.time()))

        sig_data_bytes = timestamp_bytes + json.dumps(field_value).encode('ascii')
        sig_data = base64.urlsafe_b64encode(sig_data_bytes).decode('ascii')

        signature_bytes = await wallet.crypto.crypto_sign(my_verkey, sig_data_bytes)
        signature = base64.urlsafe_b64encode(
            signature_bytes
        ).decode('ascii')

        return {
            "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/signature/1.0/ed25519Sha512_single",
            "signer": my_verkey,
            "sig_data": sig_data,
            "signature": signature
        }

    @staticmethod
    async def verify_signed_field(wallet: DynamicWallet, signed_field: dict) -> (Any, bool):
        signature_bytes = base64.urlsafe_b64decode(signed_field['signature'].encode('ascii'))
        sig_data_bytes = base64.urlsafe_b64decode(signed_field['sig_data'].encode('ascii'))
        sig_verified = await wallet.crypto.crypto_verify(
            signed_field['signer'],
            sig_data_bytes,
            signature_bytes
        )
        data_bytes = base64.urlsafe_b64decode(signed_field['sig_data'])
        timestamp = struct.unpack(">Q", data_bytes[:8])
        field_json = data_bytes[8:]
        if isinstance(field_json, bytes):
            field_json = field_json.decode('utf-8')
        return json.loads(field_json), sig_verified

    def extract_their_info(self, key: str):
        """ Extract the other participant's DID, verkey and endpoint

        :param key: attribute for extracting
        :return: Return a 4-tuple of (DID, verkey, endpoint, routingKeys)
        """
        return None
        their_did = BasicMessage.extract_did(msg, key)
        did_doc = BasicMessage.extract_did_doc(msg, key)
        service = DIDDoc.extract_service(did_doc)
        their_endpoint = service['serviceEndpoint']
        public_keys = did_doc['publicKey']

        def get_key(controller_: str, id_: str):
            for k in public_keys:
                if k['controller'] == controller_ and k["id"] == id_:
                    return k['publicKeyBase58']
            return None

        def extract_key(name: str):
            if "#" in name:
                controller_, id_ = name.split('#')
                return get_key(controller_, id_)
            else:
                return name

        their_vk = extract_key(service["recipientKeys"][0])

        routing_keys = []
        for rk in service.get("routingKeys", []):
            routing_keys.append(extract_key(rk))

        return their_did, their_vk, their_endpoint, routing_keys


class InvitationMessage(ConnProtocolMessage, metaclass=AriesProtocolMeta):

    NAME = 'invitation'

    def __init__(
            self, label: Optional[str]=None, recipient_keys: Optional[List[str]]=None,
            endpoint: Optional[str]=None, routing_keys: Optional[List[str]]=None, *args, **kwargs
    ):
        super(InvitationMessage, self).__init__(*args, **kwargs)
        if label is not None:
            self['label'] = label
        if recipient_keys is not None:
            self['recipientKeys'] = recipient_keys
        if endpoint is not None:
            self['serviceEndpoint'] = endpoint
        if routing_keys is not None:
            self['routingKeys'] = routing_keys

    @classmethod
    def from_invitation_url(cls, url: str) -> ConnProtocolMessage:
        matches = re.match("(.+)?c_i=(.+)", url)
        if not matches:
            raise SiriusInvalidMessage("Invite string is improperly formatted")
        msg = Message.deserialize(base64.urlsafe_b64decode(matches.group(2)).decode('utf-8'))
        if msg.type.protocol != cls.PROTOCOL:
            raise SiriusInvalidMessage('Unexpected protocol "%s"' % msg.type.protocol)
        if msg.type.name != cls.NAME:
            raise SiriusInvalidMessage('Unexpected protocol name "%s"' % msg.type.name)
        label = msg.pop('label', defaul=None)
        if label is None:
            raise SiriusInvalidMessage('label attribute missing')
        recipient_keys = msg.pop('recipientKeys', default=None)
        if recipient_keys is None:
            raise SiriusInvalidMessage('recipientKeys attribute missing')
        endpoint = msg.pop('serviceEndpoint', default=None)
        if endpoint is None:
            raise SiriusInvalidMessage('serviceEndpoint attribute missing')
        routing_keys = msg.pop('routingKeys', default=[])
        return InvitationMessage(label, recipient_keys, endpoint, routing_keys, **msg)

    @property
    def invitation_url(self):
        b64_invite = base64.urlsafe_b64encode(self.serialize()).decode('ascii')
        return '?c_i=' + b64_invite

    @property
    def label(self) -> str:
        return self.get('label', None)

    @property
    def recipient_keys(self) -> List[str]:
        return self.get('recipientKeys', [])

    @property
    def endpoint(self) -> str:
        return self.get('serviceEndpoint', None)

    @property
    def routing_keys(self) -> List[str]:
        return self.get('routingKeys', [])


class ConnRequestMessage(ConnProtocolMessage, metaclass=AriesProtocolMeta):

    NAME = 'request'
