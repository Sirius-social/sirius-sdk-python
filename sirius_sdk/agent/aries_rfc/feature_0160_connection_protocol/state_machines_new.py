import logging

import sirius_sdk
from sirius_sdk.errors.exceptions import SiriusValidationError
from sirius_sdk.agent.pairwise import Pairwise, TheirEndpoint
from sirius_sdk.agent.agent import Endpoint
from sirius_sdk.agent.sm import AbstractStateMachine, StateMachineAborted
from sirius_sdk.agent.aries_rfc.feature_0015_acks import Ack, Status
from sirius_sdk.agent.aries_rfc.feature_0048_trust_ping import Ping
from sirius_sdk.agent.aries_rfc.feature_0160_connection_protocol.messages import *


# Problem codes
REQUEST_NOT_ACCEPTED = "request_not_accepted"
REQUEST_PROCESSING_ERROR = 'request_processing_error'
RESPONSE_NOT_ACCEPTED = "response_not_accepted"
RESPONSE_PROCESSING_ERROR = 'response_processing_error'


class Inviter:
    """Implementation of Inviter role of the Aries connection protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
    """

    def __init__(self, me: Pairwise.Me, connection_key: str, my_endpoint: Endpoint, time_to_live: int = 60):
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

    async def create_connection(self,  request: ConnRequest) -> (bool, Pairwise):
        try:
            try:
                request.validate()
            except SiriusValidationError as e:
                # TODO
                pass
            their_did, their_vk, their_endpoint_address, their_routing_keys = request.extract_their_info()
            invitee_endpoint = TheirEndpoint(
                endpoint=their_endpoint_address,
                verkey=their_vk,
                routing_keys=their_routing_keys
            )
            co = sirius_sdk.CoProtocolAnon(
                my_verkey=self.me.verkey,
                endpoint=invitee_endpoint,
                time_to_live=self.time_to_live
            )
            response = ConnResponse(did=self.me.did, verkey=self.me.verkey, endpoint=self.my_endpoint.address)
            my_did_doc = response.did_doc
            await response.sign_connection(sirius_sdk.Crypto, self.connection_key)
            response.please_ack = True
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
                    self.__problem_report = ConnProblemReport(
                        problem_code=REQUEST_PROCESSING_ERROR,
                        explain='Expect for connection response ack. Unexpected message type "%s"' % str(response.type),
                    )
                    await co.send(self.__problem_report)
                    return False, None
            else:
                self.__problem_report = ConnProblemReport(
                    problem_code=REQUEST_PROCESSING_ERROR,
                    explain='Response ack awaiting was terminated by timeout',
                )
                await co.send(self.__problem_report)
                return False, None
        finally:
            pass


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
        try:
            try:
                invitation.validate()
            except SiriusValidationError as e:
                # TODO
                pass

            doc_uri = invitation.doc_uri
            # Extract Inviter connection_key
            connection_key = invitation.recipient_keys[0]
            inviter_endpoint = TheirEndpoint(
                endpoint=invitation.endpoint,
                verkey=connection_key
            )

            # Allocate transport channel between self and theirs by verkeys factor
            co = sirius_sdk.CoProtocolAnon(self.me.verkey, inviter_endpoint, self.time_to_live)
            request = ConnRequest(
                label=my_label,
                did=self.me.did,
                verkey=self.me.verkey,
                endpoint=self.my_endpoint.address,
                doc_uri=doc_uri
            )

            ok, response = await co.switch(request)

        finally:
            pass
