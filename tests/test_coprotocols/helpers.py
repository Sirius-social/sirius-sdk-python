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