import datetime
import uuid

from sirius_sdk.agent.aries_rfc.mixins import *


def test_feature_0032_timing_decorator():
    # Check creation
    now = datetime.datetime.now()
    timing1 = TimingMixin.Timing(
        in_time='2019-01-23 18:03:27.123Z', delay_milli=1000, expires_time=now, any_field='ANY'
    )
    assert timing1.in_time == parse_datetime('2019-01-23 18:03:27.123Z')
    assert timing1.delay_milli == 1000
    assert timing1.expires_time == now
    assert timing1.wait_until_time is None

    # Check to_json
    js = timing1.to_json()
    timing2 = TimingMixin.Timing(**js)
    assert timing1 == timing2

    # Check update
    timing3 = timing2.create_from_json(
        dict(in_time='2019-01-24 00:00Z', delay_milli=2000, any_field='ANY', stale_time='2019-01-24 18:25Z')
    )
    assert timing3.in_time == parse_datetime('2019-01-24 00:00Z')
    assert timing3.delay_milli == 2000
    assert timing3.expires_time == now
    assert timing3.stale_time == parse_datetime('2019-01-24 18:25Z')

    # Check update clear field
    timing4 = timing2.create_from_json(dict(in_time=None))
    assert timing4.in_time is None


def test_feature_0032_timing_message():
    msg = Message({
        '@id': uuid.uuid4().hex,
        '@type': 'https://didcomm.org/protocol/1.0/message-x',
        '~timing': {
            "in_time": "2019-01-23 18:03:27.123Z",
            "out_time": "2019-01-23 18:03:27.123Z",
            "stale_time": "2019-01-24 18:25Z",
            "expires_time": "2019-01-25 18:25Z",
            "delay_milli": 12345,
            "wait_until_time": "2019-01-24 00:00Z"
        }
    })
    # Get
    timing = TimingMixin.get_timing(msg)
    assert timing.in_time == parse_datetime("2019-01-23 18:03:27.123Z")
    assert timing.delay_milli == 12345
    assert timing.wait_until_time == parse_datetime("2019-01-24 00:00Z")

    # Set
    now = datetime.datetime.now()
    TimingMixin.set_timing(msg, TimingMixin.Timing(in_time=now))
    timing = TimingMixin.get_timing(msg)
    assert timing.in_time == now
    assert timing.delay_milli is None
    assert timing.wait_until_time is None

    # Clear
    TimingMixin.set_timing(msg, None)
    assert TIMING_DECORATOR not in msg
    timing = TimingMixin.get_timing(msg)
    assert timing is None
