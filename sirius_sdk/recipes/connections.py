from typing import Union, Optional

import sirius_sdk
from sirius_sdk.errors.exceptions import SiriusTimeoutIO


async def accept_invitation(url: str, me: sirius_sdk.Pairwise.Me, my_label: str) -> sirius_sdk.Pairwise:
    """Call this method to accept Inviter invitation that was income via URL/QR
    """
    my_endpoints = await sirius_sdk.endpoints()
    default_endpoint = [e for e in my_endpoints if not e.routing_keys][0]
    inv = sirius_sdk.aries_rfc.Invitation.from_url(url)
    proto = sirius_sdk.aries_rfc.Invitee(
        me=me,
        my_endpoint=default_endpoint
    )
    # Run protocol state-machine
    success, p2p = await proto.create_connection(
        invitation=inv,
        my_label=my_label
    )
    if success:
        return p2p
    else:
        raise RuntimeError(proto.problem_report.explain)


class InvitationManager:
    """Helper for Inviters to manage self connection-keys and P2P connections
    """

    def __init__(
            self, me: sirius_sdk.Pairwise.Me, my_label: str,
            connection_key: str = None, endpoint: sirius_sdk.Endpoint = None
    ):
        """
        :param me: My Identity
        :param my_label: My printable label
        :param connection_key: connection key to identify invitation
        :param endpoint: working end
        """
        self.__me = me
        self.__my_label = my_label
        self.__endpoint = endpoint
        self.__connection_key = connection_key

    @property
    def me(self) -> sirius_sdk.Pairwise.Me:
        return self.__me

    @property
    def my_label(self) -> str:
        return self.__my_label

    @property
    def connection_key(self) -> Optional[str]:
        return self.__connection_key

    @property
    def endpoint(self) -> Optional[sirius_sdk.Endpoint]:
        return self.__endpoint

    async def make_invitation(self) -> sirius_sdk.aries_rfc.Invitation:
        """Generate Invitation instance:
          - extract invitation-url
          - send QR to participants
        """
        if self.__connection_key is None:
            self.__connection_key = await sirius_sdk.Crypto.create_key()
        if self.__endpoint is None:
            my_endpoints = await sirius_sdk.endpoints()
            default_endpoints = [e for e in my_endpoints if not e.routing_keys]
            if default_endpoints:
                self.__endpoint = default_endpoints[0]
            else:
                self.__endpoint = my_endpoints[0]
        inv = sirius_sdk.aries_rfc.Invitation(
            label=self.__my_label, recipient_keys=[self.connection_key],
            endpoint=self.endpoint.address, routing_keys=self.__endpoint.routing_keys
        )
        return inv

    async def wait_connection(
            self, invitation: sirius_sdk.aries_rfc.Invitation, timeout: float = None
    ) -> sirius_sdk.Pairwise:
        """Wait incoming conn-requests for Invitation created earlier

        :param invitation: Invitation instance
        :param timeout: time until
        :return: P2P
        """
        co = await sirius_sdk.spawn_coprotocol()
        await co.subscribe_ext(
            sender_vk=[],
            recipient_vk=invitation.recipient_keys,
            protocols=[invitation.PROTOCOL]
        )
        try:
            while True:
                event = await co.get_message(timeout)
                if isinstance(event.message, sirius_sdk.aries_rfc.ConnRequest):
                    connection_key = event.recipient_verkey
                    proto = sirius_sdk.aries_rfc.Inviter(
                        me=self.me, connection_key=connection_key, my_endpoint=self.__endpoint
                    )
                    success, p2p = await proto.create_connection(request=event.message)
                    if success:
                        return p2p
                    else:
                        raise RuntimeError(proto.problem_report.explain)
        finally:
            await co.abort()
