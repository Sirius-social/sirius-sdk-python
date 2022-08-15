from typing import Optional

from sirius_sdk import Pairwise
from sirius_sdk.agent import Pong, Ping
from sirius_sdk.hub.coprotocols import CoProtocolThreadedP2P


async def ping_their(their: Pairwise, comment: str = None, wait_timeout: int = 15) -> (bool, Optional[Pong]):
    """Send pin g to remote participant and wait ong response"""
    ping = Ping(
        comment=comment,
        response_requested=True
    )
    co = CoProtocolThreadedP2P(
        thid=ping.id,
        to=their,
        time_to_live=wait_timeout
    )
    success, pong = await co.switch(ping)
    if success and isinstance(pong, Pong):
        return True, pong
    else:
        return False, None
