import json
import logging

from sirius_sdk.agent.pairwise import Pairwise, TheirEndpoint
from sirius_sdk.agent.agent import Endpoint
from sirius_sdk.agent.sm import AbstractStateMachine
from sirius_sdk.agent.aries_rfc.feature_0015_acks import Ack, Status
from sirius_sdk.agent.aries_rfc.feature_0048_trust_ping import Ping
from sirius_sdk.agent.aries_rfc.feature_0160_connection_protocol.messages import *


# Problem codes
REQUEST_NOT_ACCEPTED = "request_not_accepted"
REQUEST_PROCESSING_ERROR = 'request_processing_error'
RESPONSE_NOT_ACCEPTED = "response_not_accepted"
RESPONSE_PROCESSING_ERROR = 'response_processing_error'


class Inviter(AbstractStateMachine):

    def __init__(self, *args, **kwargs):
        self.__problem_report = None
        super().__init__(*args, **kwargs)

    @property
    def protocols(self) -> List[str]:
        return [ConnProtocolMessage.PROTOCOL, Ack.PROTOCOL]

    @property
    def problem_report(self) -> ConnProblemReport:
        return self.__problem_report

    async def create_connection(
            self, me: Pairwise.Me, connection_key: str, request: ConnRequest, my_endpoint: Endpoint
    ) -> (bool, Pairwise):
        # Validate request
        request.validate()
        self.__problem_report = None
        # Step 1: Extract their info from connection request
        their_did, their_vk, their_endpoint_address, their_routing_keys = request.extract_their_info()
        invitee_endpoint = TheirEndpoint(
            endpoint=their_endpoint_address,
            verkey=their_vk,
            routing_keys=their_routing_keys
        )
        # Allocate transport channel between self and theirs by verkeys factor
        transport = await self.transports.spawn(me.verkey, invitee_endpoint)
        await transport.start(self.protocols, self.time_to_live)
        try:
            # Step 2: build connection response
            response = ConnResponse(did=me.did, verkey=me.verkey, endpoint=my_endpoint.address)
            if request.please_ack:
                response.thread_id = request.ack_message_id
            my_did_doc = response.did_doc
            await response.sign_connection(transport.wallet.crypto, connection_key)
            response.please_ack = True
            ok, ack = await transport.switch(response)
            if ok:
                if isinstance(ack, Ack) or isinstance(ack, Ping):
                    # Step 3: store their did
                    await transport.wallet.did.store_their_did(their_did, their_vk)
                    # Step 4: create pairwise
                    their = Pairwise.Their(
                        did=their_did,
                        label=request.label,
                        endpoint=their_endpoint_address,
                        verkey=their_vk,
                        routing_keys=their_routing_keys
                    )
                    metadata = {
                        'me': {
                            'did': me.did,
                            'verkey': me.verkey,
                            'did_doc': dict(my_did_doc)
                        },
                        'their': {
                            'did': their_did,
                            'verkey': their_vk,
                            'label': request.label,
                            'endpoint': {
                                'address': their_endpoint_address,
                                'routing_keys': their_routing_keys
                            },
                            'did_doc': dict(request.did_doc)
                        }
                    }
                    pairwise = Pairwise(me=me, their=their, metadata=metadata)
                    return True, pairwise
                elif isinstance(response, ConnProblemReport):
                    self.__problem_report = response
                    logging.error('Code: %s; Explain: %s' % (response.problem_code, response.explain))
                    return False, None
                else:
                    self.__problem_report = ConnProblemReport(
                        problem_code=REQUEST_PROCESSING_ERROR,
                        explain='Expect for connection response ack. Unexpected message type "%s"' % str(response.type),
                        thread_id=request.id
                    )
                    await transport.send(self.__problem_report)
                    return False, None
            else:
                self.__problem_report = ConnProblemReport(
                    problem_code=REQUEST_PROCESSING_ERROR,
                    explain='Response ack awaiting was terminated by timeout',
                    thread_id=request.id
                )
                await transport.send(self.__problem_report)
                return False, None
        finally:
            await transport.stop()


class Invitee(AbstractStateMachine):

    def __init__(self, *args, **kwargs):
        self.__problem_report = None
        super().__init__(*args, **kwargs)

    @property
    def protocols(self) -> List[str]:
        return [ConnProtocolMessage.PROTOCOL, Ack.PROTOCOL]

    @property
    def problem_report(self) -> ConnProblemReport:
        return self.__problem_report

    async def create_connection(
            self, me: Pairwise.Me, invitation: Invitation, my_label: str, my_endpoint: Endpoint
    ) -> (bool, Pairwise):
        # Validate invitation
        invitation.validate()
        self.__problem_report = None
        # Extract Inviter connection_key
        connection_key = invitation.recipient_keys[0]
        inviter_endpoint = TheirEndpoint(
            endpoint=invitation.endpoint,
            verkey=connection_key
        )
        # Allocate transport channel between self and theirs by verkeys factor
        transport = await self.transports.spawn(me.verkey, inviter_endpoint)
        await transport.start(self.protocols, self.time_to_live)
        try:
            # Step 1: send connection request to Inviter
            request = ConnRequest(
                label=my_label,
                did=me.did,
                verkey=me.verkey,
                endpoint=my_endpoint.address
            )
            request.please_ack = True
            ok, response = await transport.switch(request)
            if ok:
                if isinstance(response, ConnResponse):
                    # Step 2: process connection response from Inviter
                    success = await response.verify_connection(transport.wallet.crypto)
                    try:
                        response.validate()
                    except SiriusValidationError:
                        success = False
                    if success and (response['connection~sig']['signer'] == connection_key):
                        # Step 3: extract Inviter info and store did
                        their_did, their_vk, their_endpoint_address, their_routing_keys = response.extract_their_info()
                        await transport.wallet.did.store_their_did(their_did, their_vk)
                        # Step 4: Send ack to Inviter
                        if response.please_ack:
                            ack = Ack(thread_id=response.id, status=Status.OK)
                            await transport.send(ack)
                        else:
                            ping = Ping(comment='Connection established', response_requested=False)
                            await transport.send(ping)
                        # Step 5: Make Pairwise instance
                        their = Pairwise.Their(
                            did=their_did,
                            label=invitation.label,
                            endpoint=their_endpoint_address,
                            verkey=their_vk,
                            routing_keys=their_routing_keys
                        )
                        metadata = {
                            'me': {
                                'did': me.did,
                                'verkey': me.verkey,
                                'did_doc': dict(request.did_doc)
                            },
                            'their': {
                                'did': their_did,
                                'verkey': their_vk,
                                'label': invitation.label,
                                'endpoint': {
                                    'address': their_endpoint_address,
                                    'routing_keys': their_routing_keys
                                },
                                'did_doc': dict(response.did_doc)
                            }
                        }
                        pairwise = Pairwise(me=me, their=their, metadata=metadata)
                        return True, pairwise
                    else:
                        self.__problem_report = ConnProblemReport(
                            problem_code=RESPONSE_NOT_ACCEPTED,
                            explain='Invalid connection response signature for connection_key: "%s"' % connection_key,
                            thread_id=response.id
                        )
                        await transport.send(self.__problem_report)
                        return False, None
                elif isinstance(response, ConnProblemReport):
                    self.__problem_report = response
                    logging.error('Code: %s; Explain: %s' % (response.problem_code, response.explain))
                    return False, None
                else:
                    self.__problem_report = ConnProblemReport(
                        problem_code=RESPONSE_NOT_ACCEPTED,
                        explain='Expect for connection response. Unexpected message type "%s"' % str(response.type),
                        thread_id=response.id
                    )
                    await transport.send(self.__problem_report)
                    return False, None
            else:
                self.__problem_report = ConnProblemReport(
                    problem_code=RESPONSE_PROCESSING_ERROR,
                    explain='Response awaiting was terminated by timeout',
                )
                await transport.send(self.__problem_report)
                return False, None
        finally:
            await transport.stop()
