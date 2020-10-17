import datetime
from typing import Optional

import sirius_sdk
from sirius_sdk.hub import CoProtocolThreadedP2P
from sirius_sdk.agent.pairwise import Pairwise
from sirius_sdk.errors.exceptions import SiriusTimeoutIO

from ..feature_0015_acks import Ack
from .messages import Question, Answer


async def ask_and_wait_answer(query: Question, to: Pairwise) -> (bool, Optional[Answer]):
    iso_string = query.expires_time
    if iso_string:
        try:
            expires_at = datetime.datetime.fromisoformat(iso_string)
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
            delta = expires_at.replace(tzinfo=None) - datetime.datetime.utcnow().replace(tzinfo=None)
            ttl = round(delta.total_seconds())
        except Exception as e:
            ttl = None
    else:
        ttl = None

    co = CoProtocolThreadedP2P(
        thid=query.id,
        to=to,
        time_to_live=ttl
    )
    await co.send(query)
    try:
        while True:
            msg, sender_verkey, recipient_verkey = await co.get_one()
            if (sender_verkey == to.their.verkey) and isinstance(msg, Answer):
                return True, msg
    except SiriusTimeoutIO:
        return False, None


async def make_answer(response: str, q: Question, to: Pairwise):
    answer = Answer(
        response=response,
        thread_id=q.id
    )
    answer.set_out_time()
    await sirius_sdk.send_to(answer, to)
