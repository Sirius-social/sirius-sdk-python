
from ....agent.pairwise import Pairwise, TheirEndpoint
from ....agent.agent import Endpoint
from ..base import AbstractStateMachine
from ..feature_0015_acks import Ack, Status
from .messages import *


class Inviter(AbstractStateMachine):

    @property
    def protocols(self) -> List[str]:
        return [ConnProtocolMessage.PROTOCOL, Ack.PROTOCOL]

    async def create_connection(
            self, me: Pairwise.Me, connection_key: str, request: ConnRequest, my_endpoint: Endpoint
    ) -> Pairwise:
        their_did, their_vk, their_endpoint, their_routing_keys = request.extract_their_info()
        invitee_endpoint = TheirEndpoint(
            endpoint=their_endpoint,
            verkey=their_vk,
            routing_keys=their_routing_keys
        )
        transport = await self.transport.spawn(connection_key, invitee_endpoint)
        await transport.start(self.protocols, self.time_to_live)
        try:
            # Step 1: build connection response
            response = ConnResponse(did=me.did, verkey=me.verkey, endpoint=my_endpoint.address)
            await response.sign_connection(transport.wallet.crypto, connection_key)
            response.please_ack = True
            print('@')
            ok, ack = await transport.switch(response)
            print('!')
        finally:
            await transport.stop()


class Invitee(AbstractStateMachine):

    @property
    def protocols(self) -> List[str]:
        return [ConnProtocolMessage.PROTOCOL, Ack.PROTOCOL]

    async def create_connection(
            self, me: Pairwise.Me, invitation: Invitation, my_label: str, my_endpoint: Endpoint
    ) -> Pairwise:
        connection_key = invitation.recipient_keys[0]
        inviter_endpoint = TheirEndpoint(
            endpoint=invitation.endpoint,
            verkey=connection_key
        )
        transport = await self.transport.spawn(me.verkey, inviter_endpoint)
        await transport.start(self.protocols, self.time_to_live)
        try:
            # Step 1: send connection request to Inviter
            request = ConnRequest(
                label=my_label,
                did=me.did,
                verkey=me.verkey,
                endpoint=my_endpoint.address
            )
            ok, response = await transport.switch(request)
            print('!')
            await response.verify_connection(transport.wallet.crypto)
            print('@')
            if response.please_ack:
                ack = Ack(thread_id=response.id)
                await transport.send(ack)
        finally:
            await transport.stop()
