TEST_MSG_TYPES = [
    'https://didcomm.org/test_protocol/1.0/request-1',
    'https://didcomm.org/test_protocol/1.0/response-1',
    'https://didcomm.org/test_protocol/1.0/request-2',
    'https://didcomm.org/test_protocol/1.0/response-2',
]
MSG_LOG = []


def check_msg_log():
    assert len(MSG_LOG) == len(TEST_MSG_TYPES)
    for i, item in enumerate(TEST_MSG_TYPES):
        assert MSG_LOG[i].type == TEST_MSG_TYPES[i]
    assert MSG_LOG[0]['content'] == 'Request1'
    assert MSG_LOG[1]['content'] == 'Response1'
    assert MSG_LOG[2]['content'] == 'Request2'
    assert MSG_LOG[3]['content'] == 'End'


def check_thread_orders():
    orders_under_checks = {}
    for i, item in enumerate(MSG_LOG):
        decorator = item.get('~thread', {}).get('received_orders', {})
        for recipient, order in decorator.items():
            if recipient in orders_under_checks:
                last_order = orders_under_checks[recipient]
                new_order = order
                assert new_order == last_order + 1
            else:
                orders_under_checks[recipient] = order
