from sirius_sdk.messaging import *


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
