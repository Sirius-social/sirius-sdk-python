import uuid

import pytest

from sirius_sdk.errors.exceptions import SiriusTimeoutIO
from sirius_sdk.hub.defaults.inmemory_bus import InMemoryBus


@pytest.mark.asyncio
async def test_sane():
    session1 = InMemoryBus()
    session2 = InMemoryBus()
    thid1 = 'thread-' + uuid.uuid4().hex
    thid2 = 'thread-' + uuid.uuid4().hex
    content1 = b'Message-1'
    content2 = b'Message-2'

    # Subscribe from session-2
    for thid in [thid1, thid2]:
        ok = await session2.subscribe(thid)
        assert ok is True
    # Publish from session-1
    for thid, content in [(thid1, content1), (thid2, content2)]:
        num = await session1.publish(thid, content)
        assert num > 0
    # Retrieve from session-2
    for n in range(2):
        event = await session2.get_event(timeout=3)
        assert event.payload in [content1, content2]
    # Unsubscribe from thread-2
    await session2.unsubscribe(thid1)
    # Publish again
    for thid, num_expected in [(thid1, 0), (thid2, 1)]:
        num = await session1.publish(thid, content)
        assert num == num_expected
    # Retrieve from session-2
    event = await session2.get_event(timeout=3)
    assert event.payload == content2
    with pytest.raises(SiriusTimeoutIO):
        await session2.get_event(timeout=3)
