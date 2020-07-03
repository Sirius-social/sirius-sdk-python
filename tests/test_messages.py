from sirius_sdk.messaging import *
from sirius_sdk.agent.aries_rfc.feature_0048_trust_ping.messages import Ping, Pong


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
        }
    )
    assert ok is True
    assert isinstance(pong, Pong)
    assert pong.comment == 'Hi. I am OK!'
