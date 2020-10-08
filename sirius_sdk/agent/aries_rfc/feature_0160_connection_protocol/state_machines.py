import json
import logging

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


class Inviter(AbstractStateMachine):
    """Implementation of Inviter role of the Aries connection protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
    """

    def __init__(self, *args, **kwargs):
        self.__problem_report = None
        self.__transport = None
        self.__thread_id = None
        super().__init__(*args, **kwargs)

    @property
    def protocols(self) -> List[str]:
        return [ConnProtocolMessage.PROTOCOL, Ack.PROTOCOL, Ping.PROTOCOL]

    @property
    def problem_report(self) -> ConnProblemReport:
        return self.__problem_report

    async def create_connection(
            self, me: Pairwise.Me, connection_key: str, request: ConnRequest, my_endpoint: Endpoint
    ) -> (bool, Pairwise):
        # Validate request
        await self.log(progress=0, message='Validate request', payload=dict(request), connection_key=connection_key)
        request.validate()
        await self.log(progress=20, message='Request validation OK')
        self.__thread_id = request.ack_message_id
        self.__problem_report = None
        # Step 1: Extract their info from connection request
        await self.log(progress=40, message='Step-1: Extract their info from connection request')
        their_did, their_vk, their_endpoint_address, their_routing_keys = request.extract_their_info()
        invitee_endpoint = TheirEndpoint(
            endpoint=their_endpoint_address,
            verkey=their_vk,
            routing_keys=their_routing_keys
        )
        # Allocate transport channel between self and theirs by verkeys factor
        self.__transport = await self.transports.spawn(me.verkey, invitee_endpoint)
        await self.__transport.start(self.protocols, self.time_to_live)
        await self.log(progress=60, message='Transport channel is allocated')
        try:
            # Step 2: build connection response
            response = ConnResponse(did=me.did, verkey=me.verkey, endpoint=my_endpoint.address)
            if request.please_ack:
                response.thread_id = request.ack_message_id
            my_did_doc = response.did_doc
            await response.sign_connection(self.__transport.wallet.crypto, connection_key)
            response.please_ack = True
            await self.log(progress=80, message='Step-2: Connection response', payload=dict(response))
            ok, ack = await self.__transport.switch(response)
            if self.is_aborted:
                await self.log(progress=100, message='Aborted')
                raise StateMachineAborted
            if ok:
                if isinstance(ack, Ack) or isinstance(ack, Ping):
                    # Step 3: store their did
                    await self.log(progress=90, message='Step-3: Ack received, store their DID')
                    await self.__transport.wallet.did.store_their_did(their_did, their_vk)
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
                    await self.log(progress=100, message='Pairwise established', payload=metadata)
                    return True, pairwise
                elif isinstance(response, ConnProblemReport):
                    self.__problem_report = response
                    logging.error('Code: %s; Explain: %s' % (response.problem_code, response.explain))
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=self.__problem_report.problem_code, explain=self.__problem_report.explain
                    )
                    return False, None
                else:
                    self.__problem_report = ConnProblemReport(
                        problem_code=REQUEST_PROCESSING_ERROR,
                        explain='Expect for connection response ack. Unexpected message type "%s"' % str(response.type),
                        thread_id=self.__thread_id
                    )
                    await self.__transport.send(self.__problem_report)
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=self.__problem_report.problem_code, explain=self.__problem_report.explain
                    )
                    return False, None
            else:
                self.__problem_report = ConnProblemReport(
                    problem_code=REQUEST_PROCESSING_ERROR,
                    explain='Response ack awaiting was terminated by timeout',
                    thread_id=self.__thread_id
                )
                await self.__transport.send(self.__problem_report)
                await self.log(
                    progress=100, message=f'Terminated with error',
                    problem_code=self.__problem_report.problem_code, explain=self.__problem_report.explain
                )
                return False, None
        finally:
            await self.__transport.stop()
            self.__transport = None

    async def abort(self):
        await super().abort()
        if self.__transport and self.__transport.is_started:
            self.__problem_report = ConnProblemReport(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Operation is aborted by owner',
                thread_id=self.__thread_id
            )
            await self.__transport.send(self.__problem_report)


class Invitee(AbstractStateMachine):
    """Implementation of Invitee role of the Aries connection protocol

    See details: https://github.com/hyperledger/aries-rfcs/tree/master/features/0160-connection-protocol
    """

    def __init__(self, *args, **kwargs):
        self.__problem_report = None
        self.__transport = None
        self.__thread_id = None
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
        await self.log(progress=0, message='Invitation validate', payload=dict(invitation))
        invitation.validate()
        await self.log(progress=20, message='Invitation validation OK')
        doc_uri = invitation.doc_uri
        self.__problem_report = None
        # Extract Inviter connection_key
        connection_key = invitation.recipient_keys[0]
        inviter_endpoint = TheirEndpoint(
            endpoint=invitation.endpoint,
            verkey=connection_key
        )
        # Allocate transport channel between self and theirs by verkeys factor
        self.__transport = await self.transports.spawn(me.verkey, inviter_endpoint)
        await self.__transport.start(self.protocols, self.time_to_live)
        await self.log(progress=40, message='Transport channel is allocated')
        try:
            # Step 1: send connection request to Inviter
            request = ConnRequest(
                label=my_label,
                did=me.did,
                verkey=me.verkey,
                endpoint=my_endpoint.address,
                doc_uri=doc_uri
            )
            request.please_ack = True
            self.__thread_id = request.ack_message_id
            await self.log(progress=50, message='Step-1: send connection request to Inviter', payload=dict(request))
            ok, response = await self.__transport.switch(request)
            if self.is_aborted:
                await self.log(progress=100, message='Aborted')
                raise StateMachineAborted
            if ok:
                if isinstance(response, ConnResponse):
                    # Step 2: process connection response from Inviter
                    await self.log(
                        progress=40,
                        message='Step-2: process connection response from Inviter',
                        payload=dict(request)
                    )
                    success = await response.verify_connection(self.__transport.wallet.crypto)
                    try:
                        response.validate()
                    except SiriusValidationError:
                        success = False
                    if success and (response['connection~sig']['signer'] == connection_key):
                        # Step 3: extract Inviter info and store did
                        await self.log(progress=70, message='Step-3: extract Inviter info and store DID')
                        their_did, their_vk, their_endpoint_address, their_routing_keys = response.extract_their_info()
                        await self.__transport.wallet.did.store_their_did(their_did, their_vk)
                        # Step 4: Send ack to Inviter
                        if response.please_ack:
                            ack = Ack(thread_id=response.id, status=Status.OK)
                            await self.log(progress=90, message='Step-4: Send ack to Inviter')
                            await self.__transport.send(ack)
                        else:
                            ping = Ping(comment='Connection established', response_requested=False)
                            await self.log(progress=90, message='Step-4: Send ping to Inviter')
                            await self.__transport.send(ping)
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
                        await self.log(progress=100, message='Pairwise established', payload=metadata)
                        return True, pairwise
                    else:
                        self.__problem_report = ConnProblemReport(
                            problem_code=RESPONSE_NOT_ACCEPTED,
                            explain='Invalid connection response signature for connection_key: "%s"' % connection_key,
                            thread_id=response.id
                        )
                        await self.__transport.send(self.__problem_report)
                        await self.log(
                            progress=100, message=f'Terminated with error',
                            problem_code=self.__problem_report.problem_code, explain=self.__problem_report.explain
                        )
                        return False, None
                elif isinstance(response, ConnProblemReport):
                    self.__problem_report = response
                    logging.error('Code: %s; Explain: %s' % (response.problem_code, response.explain))
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=self.__problem_report.problem_code, explain=self.__problem_report.explain
                    )
                    return False, None
                else:
                    self.__problem_report = ConnProblemReport(
                        problem_code=RESPONSE_NOT_ACCEPTED,
                        explain='Expect for connection response. Unexpected message type "%s"' % str(response.type),
                        thread_id=response.id
                    )
                    await self.__transport.send(self.__problem_report)
                    await self.log(
                        progress=100, message=f'Terminated with error',
                        problem_code=self.__problem_report.problem_code, explain=self.__problem_report.explain
                    )
                    return False, None
            else:
                self.__problem_report = ConnProblemReport(
                    problem_code=RESPONSE_PROCESSING_ERROR,
                    explain='Response awaiting was terminated by timeout',
                )
                await self.__transport.send(self.__problem_report)
                await self.log(
                    progress=100, message=f'Terminated with error',
                    problem_code=self.__problem_report.problem_code, explain=self.__problem_report.explain
                )
                return False, None
        finally:
            await self.__transport.stop()
            self.__transport = None

    async def abort(self):
        await super().abort()
        if self.__transport and self.__transport.is_started:
            self.__problem_report = ConnProblemReport(
                problem_code=REQUEST_PROCESSING_ERROR,
                explain='Operation is aborted by owner',
                thread_id=self.__thread_id
            )
            await self.__transport.send(self.__problem_report)
