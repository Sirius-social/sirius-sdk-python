import logging

import sirius_sdk
from sirius_sdk.errors.exceptions import SiriusValidationError, StateMachineAborted, StateMachineTerminatedWithError
from sirius_sdk.agent.pairwise import Pairwise, TheirEndpoint
from sirius_sdk.agent.agent import Endpoint
from sirius_sdk.agent.aries_rfc.feature_0015_acks import Ack, Status
from sirius_sdk.agent.aries_rfc.feature_0048_trust_ping import Ping
from sirius_sdk.agent.aries_rfc.feature_0160_connection_protocol.messages import *


# Problem codes
REQUEST_NOT_ACCEPTED = "request_not_accepted"
REQUEST_PROCESSING_ERROR = 'request_processing_error'
RESPONSE_NOT_ACCEPTED = "response_not_accepted"
RESPONSE_PROCESSING_ERROR = 'response_processing_error'


class Inviter(sirius_sdk.AbstractStateMachine):
    """Implementation of Inviter role of the Aries connection protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
    """

    def __init__(self, me: Pairwise.Me, connection_key: str, my_endpoint: Endpoint, time_to_live: int = 60):
        super(Inviter, self).__init__(time_to_live)
        self.__me = me
        self.__connection_key = connection_key
        self.__my_endpoint = my_endpoint
        self.__problem_report = None
        self.__time_to_live = time_to_live

    @property
    def me(self) -> Pairwise.Me:
        return self.__me

    @property
    def connection_key(self) -> str:
        return self.__connection_key

    @property
    def my_endpoint(self) -> Endpoint:
        return self.__my_endpoint

    @property
    def time_to_live(self) -> Optional[int]:
        return self.__time_to_live

    @property
    def problem_report(self) -> ConnProblemReport:
        return self.__problem_report

    async def create_connection(self, request: ConnRequest) -> (bool, Pairwise):
        request.validate()
        doc_uri = request.doc_uri
        their_did, their_vk, their_endpoint_address, their_routing_keys = request.extract_their_info()
        invitee_endpoint = TheirEndpoint(
            endpoint=their_endpoint_address,
            verkey=their_vk,
            routing_keys=their_routing_keys
        )

        co = sirius_sdk.CoProtocolAnon(
            my_verkey=self.me.verkey,
            endpoint=invitee_endpoint,
            protocols=[ConnProtocolMessage.PROTOCOL, Ack.PROTOCOL],
            time_to_live=self.time_to_live
        )
        try:
            response = ConnResponse(
                did=self.me.did,
                verkey=self.me.verkey,
                endpoint=self.my_endpoint.address,
                doc_uri=doc_uri
            )
            if request.please_ack:
                response.thread_id = request.ack_message_id
            my_did_doc = response.did_doc
            await response.sign_connection(sirius_sdk.Crypto, self.connection_key)

            ok, ack = await co.switch(response)
            if ok:
                if isinstance(ack, Ack) or isinstance(ack, Ping):
                    await sirius_sdk.DID.store_their_did(their_did, their_vk)
                    their = Pairwise.Their(
                        did=their_did,
                        label=request.label,
                        endpoint=their_endpoint_address,
                        verkey=their_vk,
                        routing_keys=their_routing_keys
                    )
                    metadata = {
                        'me': {
                            'did': self.me.did,
                            'verkey': self.me.verkey,
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
                    pairwise = Pairwise(me=self.me, their=their, metadata=metadata)
                    return True, pairwise
                elif isinstance(response, ConnProblemReport):
                    self.__problem_report = response
                    logging.error('Code: %s; Explain: %s' % (response.problem_code, response.explain))
                    return False, None
                else:
                    raise StateMachineTerminatedWithError(
                        problem_code=REQUEST_PROCESSING_ERROR,
                        explain='Expect for connection response ack. Unexpected message type "%s"' % str(response.type)
                    )
            else:
                raise StateMachineTerminatedWithError(
                    problem_code=REQUEST_PROCESSING_ERROR,
                    explain='Response ack awaiting was terminated by timeout',
                    notify=False
                )
        except StateMachineTerminatedWithError as e:
            self.__problem_report = ConnProblemReport(
                problem_code=e.problem_code,
                explain=e.explain,
            )
            if e.notify:
                await co.send(self.__problem_report)
            return False, None


class Invitee:
    """Implementation of Invitee role of the Aries connection protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
    """

    def __init__(self, me: Pairwise.Me, my_endpoint: Endpoint, time_to_live: int = 60):
        self.__problem_report = None
        self.__time_to_live = time_to_live
        self.__me = me
        self.__my_endpoint = my_endpoint

    @property
    def me(self) -> Pairwise.Me:
        return self.__me

    @property
    def my_endpoint(self) -> Endpoint:
        return self.__my_endpoint

    @property
    def problem_report(self) -> ConnProblemReport:
        return self.__problem_report

    @property
    def time_to_live(self) -> Optional[int]:
        return self.__time_to_live

    async def create_connection(self, invitation: Invitation, my_label: str) -> (bool, Pairwise):
        invitation.validate()
        doc_uri = invitation.doc_uri
        # Extract Inviter connection_key
        connection_key = invitation.recipient_keys[0]
        inviter_endpoint = TheirEndpoint(
            endpoint=invitation.endpoint,
            verkey=connection_key
        )
        # Allocate transport channel between self and theirs by verkeys factor
        co = sirius_sdk.CoProtocolAnon(
            my_verkey=self.me.verkey,
            endpoint=inviter_endpoint,
            protocols=[ConnProtocolMessage.PROTOCOL, Ack.PROTOCOL],
            time_to_live=self.time_to_live
        )

        try:
            request = ConnRequest(
                label=my_label,
                did=self.me.did,
                verkey=self.me.verkey,
                endpoint=self.my_endpoint.address,
                doc_uri=doc_uri
            )

            ok, response = await co.switch(request)
            if ok:
                if isinstance(response, ConnResponse):
                    # Step 2: process connection response from Inviter
                    success = await response.verify_connection(sirius_sdk.Crypto)
                    try:
                        response.validate()
                    except SiriusValidationError as e:
                        raise StateMachineTerminatedWithError(
                            problem_code=RESPONSE_NOT_ACCEPTED,
                            explain=e.message
                        )
                    if success and (response['connection~sig']['signer'] == connection_key):
                        # Step 3: extract Inviter info and store did
                        their_did, their_vk, their_endpoint_address, their_routing_keys = response.extract_their_info()
                        await sirius_sdk.DID.store_their_did(their_did, their_vk)
                        # Step 4: Send ack to Inviter
                        if response.please_ack:
                            ack = Ack(thread_id=response.ack_message_id, status=Status.OK)
                            await co.send(ack)
                        else:
                            ping = Ping(comment='Connection established', response_requested=False)
                            await co.send(ping)
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
                                'did': self.me.did,
                                'verkey': self.me.verkey,
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
                        pairwise = Pairwise(me=self.me, their=their, metadata=metadata)
                        return True, pairwise
                    else:
                        raise StateMachineTerminatedWithError(
                            problem_code=RESPONSE_NOT_ACCEPTED,
                            explain='Invalid connection response signature for connection_key: "%s"' % connection_key,
                        )
                elif isinstance(response, ConnProblemReport):
                    self.__problem_report = response
                    logging.error('Code: %s; Explain: %s' % (response.problem_code, response.explain))
                    return False, None
            else:
                raise StateMachineTerminatedWithError(
                    problem_code=RESPONSE_PROCESSING_ERROR,
                    explain='Response awaiting was terminated by timeout',
                    notify=False
                )

        except StateMachineTerminatedWithError as e:
            self.__problem_report = ConnProblemReport(
                problem_code=e.problem_code,
                explain=e.explain,
            )
            if e.notify:
                await co.send(self.__problem_report)
            return False, None
