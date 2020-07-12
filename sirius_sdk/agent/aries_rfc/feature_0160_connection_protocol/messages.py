r"""https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
"""
import re
import time
import json
import struct
import base64
from typing import List, Optional, Any

from ....errors.exceptions import *
from ....messaging import Message, check_for_attributes
from ....agent.wallet.abstract.crypto import AbstractCrypto
from ..base import AriesProtocolMessage, RegisterMessage, AriesProblemReport
from ..did_doc import DIDDoc


class ConnProtocolMessage(AriesProtocolMessage, metaclass=RegisterMessage):
    """Aries feature 0160 Message implementation

    https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
    """

    PROTOCOL = 'connections'

    @staticmethod
    async def sign_field(crypto: AbstractCrypto, field_value: Any, my_verkey: str) -> dict:
        timestamp_bytes = struct.pack(">Q", int(time.time()))

        sig_data_bytes = timestamp_bytes + json.dumps(field_value).encode('ascii')
        sig_data = base64.urlsafe_b64encode(sig_data_bytes).decode('ascii')

        signature_bytes = await crypto.crypto_sign(my_verkey, sig_data_bytes)
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
    async def verify_signed_field(crypto: AbstractCrypto, signed_field: dict) -> (Any, bool):
        signature_bytes = base64.urlsafe_b64decode(signed_field['signature'].encode('ascii'))
        sig_data_bytes = base64.urlsafe_b64decode(signed_field['sig_data'].encode('ascii'))
        sig_verified = await crypto.crypto_verify(
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

    @staticmethod
    def build_did_doc(did: str, verkey: str, endpoint: str):
        key_id = did + '#1'
        return {
            "@context": "https://w3id.org/did/v1",
            "id": did,
            "authentication": [
                {
                    "publicKey": key_id,
                    "type": "Ed25519SignatureAuthentication2018"
                }
            ],
            "publicKey": [{
                "id": "1",
                "type": "Ed25519VerificationKey2018",
                "controller": did,
                "publicKeyBase58": verkey
            }],
            "service": [{
                "id": 'did:peer:' + did + ";indy",
                "type": "IndyAgent",
                "priority": 0,
                "recipientKeys": [key_id],
                "serviceEndpoint": endpoint,
            }],
        }

    @property
    def their_did(self):
        return self['connection'].get('did', None) or self['connection'].get('DID')

    @property
    def did_doc(self):
        payload = self.get('connection', {}).get('did_doc', {}) or self.get('connection', {}).get('DIDDoc', None)
        return DIDDoc(payload) if payload is not None else None

    def extract_their_info(self):
        """ Extract the other participant's DID, verkey and endpoint

        :param key: attribute for extracting
        :return: Return a 4-tuple of (DID, verkey, endpoint, routingKeys)
        """
        if self.their_did is None:
            raise SiriusInvalidMessage('Connection metadata is empty')
        if self.did_doc is None:
            raise SiriusInvalidMessage('DID Doc is empty')
        service = self.did_doc.extract_service()
        their_endpoint = service['serviceEndpoint']
        public_keys = self.did_doc['publicKey']

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

        return self.their_did, their_vk, their_endpoint, routing_keys

    def validate(self):
        super().validate()
        if 'connection' in self:
            if self.did_doc is None:
                raise SiriusInvalidMessage('DIDDoc is empty')
            self.did_doc.validate()

    @property
    def please_ack(self) -> bool:
        """https://github.com/hyperledger/aries-rfcs/tree/master/features/0317-please-ack"""
        return self.get('~please_ack', None) is not None

    @please_ack.setter
    def please_ack(self, flag: bool):
        if flag:
            self['~please_ack'] = {}
        elif '~please_ack' in self:
            del self['~please_ack']


class ConnProblemReport(AriesProblemReport, metaclass=RegisterMessage):
    PROTOCOL = 'connection'


class Invitation(ConnProtocolMessage, metaclass=RegisterMessage):

    NAME = 'invitation'

    def __init__(
            self, label: Optional[str]=None, recipient_keys: Optional[List[str]]=None,
            endpoint: Optional[str]=None, routing_keys: Optional[List[str]]=None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if label is not None:
            self['label'] = label
        if recipient_keys is not None:
            self['recipientKeys'] = recipient_keys
        if endpoint is not None:
            self['serviceEndpoint'] = endpoint
        if routing_keys is not None:
            self['routingKeys'] = routing_keys

    def validate(self):
        check_for_attributes(
            self,
            ['label', 'recipientKeys', 'serviceEndpoint']
        )

    @classmethod
    def from_url(cls, url: str) -> ConnProtocolMessage:
        matches = re.match("(.+)?c_i=(.+)", url)
        if not matches:
            raise SiriusInvalidMessage("Invite string is improperly formatted")
        msg = Message.deserialize(base64.urlsafe_b64decode(matches.group(2)).decode('utf-8'))
        if msg.protocol != cls.PROTOCOL:
            raise SiriusInvalidMessage('Unexpected protocol "%s"' % msg.type.protocol)
        if msg.name != cls.NAME:
            raise SiriusInvalidMessage('Unexpected protocol name "%s"' % msg.type.name)
        label = msg.pop('label')
        if label is None:
            raise SiriusInvalidMessage('label attribute missing')
        recipient_keys = msg.pop('recipientKeys')
        if recipient_keys is None:
            raise SiriusInvalidMessage('recipientKeys attribute missing')
        endpoint = msg.pop('serviceEndpoint')
        if endpoint is None:
            raise SiriusInvalidMessage('serviceEndpoint attribute missing')
        routing_keys = msg.pop('routingKeys', [])
        return Invitation(label, recipient_keys, endpoint, routing_keys, **msg)

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


class ConnRequest(ConnProtocolMessage, metaclass=RegisterMessage):

    NAME = 'request'

    def __init__(
            self, label: Optional[str]=None, did: Optional[str]=None, verkey: Optional[str]=None,
            endpoint: Optional[str]=None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if label is not None:
            self['label'] = label
        if (did is not None) and (verkey is not None) and (endpoint is not None):
            self['connection'] = {
                'DID': did,
                'DIDDoc': self.build_did_doc(did, verkey, endpoint)
            }

    @property
    def label(self) -> Optional[str]:
        return self.get('label', None)

    def validate(self):
        super().validate()
        check_for_attributes(
            self,
            ['label', 'connection']
        )


class ConnResponse(ConnProtocolMessage, metaclass=RegisterMessage):

    NAME = 'response'

    def __init__(
            self, did: Optional[str]=None, verkey: Optional[str]=None,
            endpoint: Optional[str]=None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if (did is not None) and (verkey is not None) and (endpoint is not None):
            self['connection'] = {
                'DID': did,
                'DIDDoc': self.build_did_doc(did, verkey, endpoint)
            }

    def validate(self):
        super().validate()
        check_for_attributes(
            self,
            ['connection~sig']
        )

    async def sign_connection(self, crypto: AbstractCrypto, key: str):
        self['connection~sig'] = \
            await self.sign_field(
                crypto=crypto, field_value=self['connection'], my_verkey=key
            )
        del self['connection']

    async def verify_connection(self, crypto: AbstractCrypto) -> bool:
        connection, success = await self.verify_signed_field(
            crypto=crypto, signed_field=self['connection~sig']
        )
        if success:
            self['connection'] = connection
        return success
