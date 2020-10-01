from sirius_sdk.messaging import *
from sirius_sdk.agent.aries_rfc.feature_0048_trust_ping.messages import Ping, Pong
from sirius_sdk.agent.aries_rfc.feature_0015_acks.messages import Ack, Status as AckStatus


class Test1Message(Message):
    pass


class Test2Message(Message):
    pass


def test_register_protocol_message_success():
    register_message_class(Test1Message, protocol='test-protocol')
    ok, msg = restore_message_instance(
        {
            '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test-protocol/1.0/name'
        }
    )
    assert ok is True
    assert isinstance(msg, Test1Message)


def test_agnostic_doc_uri():
    register_message_class(Test1Message, protocol='test-protocol')
    ok, msg = restore_message_instance(
        {
            '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test-protocol/1.0/name'
        }
    )
    assert ok is True
    assert isinstance(msg, Test1Message)

    ok, msg = restore_message_instance(
        {
            '@type': 'https://didcomm.org/test-protocol/1.0/name'
        }
    )
    assert ok is True
    assert isinstance(msg, Test1Message)


def test_register_protocol_message_fail():
    register_message_class(Test1Message, protocol='test-protocol')
    ok, msg = restore_message_instance(
        {
            '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/fake-protocol/1.0/name'
        }
    )
    assert ok is False
    assert msg is None


def test_register_protocol_message_multiple_name():
    register_message_class(Test1Message, protocol='test-protocol')
    register_message_class(Test2Message, protocol='test-protocol', name='test-name')
    ok, msg = restore_message_instance(
        {
            '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test-protocol/1.0/name'
        }
    )
    assert ok is True
    assert isinstance(msg, Test1Message)

    ok, msg = restore_message_instance(
        {
            '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/test-protocol/1.0/test-name'
        }
    )
    assert ok is True
    assert isinstance(msg, Test2Message)


def test_aries_ping_pong():
    ok, ping = restore_message_instance(
        {
            '@id': 'trust-ping-message-id',
            '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping',
            "comment": "Hi. Are you OK?",
            "response_requested": True
        }
    )
    assert ok is True
    assert isinstance(ping, Ping)
    assert ping.comment == 'Hi. Are you OK?'
    assert ping.response_requested is True

    ok, pong = restore_message_instance(
        {
            '@id': 'trust-ping_response-message-id',
            '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/trust_ping/1.0/ping_response',
            "comment": "Hi. I am OK!",
            "~thread": {
                "thid": "ping-id"
            }
        }
    )
    assert ok is True
    assert isinstance(pong, Pong)
    assert pong.comment == 'Hi. I am OK!'
    assert pong.ping_id == 'ping-id'


def test_aries_ack():

    message = Ack(thread_id='ack-thread-id', status=AckStatus.PENDING)
    assert message.protocol == 'notification'
    assert message.name == 'ack'
    assert message.version == '1.0'
    assert str(message.version_info) == '1.0.0'
    assert message.status == AckStatus.PENDING
    message.validate()

    ok, ack = restore_message_instance(
        {
            '@id': 'ack-message-id',
            '@type': 'did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/notification/1.0/ack',
            'status': 'PENDING',
            "~thread": {
                'thid': 'thread-id'
            },
        }
    )
    assert ok is True
    assert isinstance(ack, Ack)
    assert ack.thread_id == 'thread-id'
    ack.validate()
    assert ack.status == AckStatus.PENDING

