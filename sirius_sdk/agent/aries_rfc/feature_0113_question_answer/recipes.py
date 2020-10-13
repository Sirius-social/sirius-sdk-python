import datetime
from typing import Optional

import sirius_sdk
from sirius_sdk.hub import CoProtocolThreaded
from sirius_sdk.agent.pairwise import Pairwise

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

    co = CoProtocolThreaded(
        thid=query.id,
        to=to,
        protocols=[Question.PROTOCOL],
        time_to_live=ttl
    )
    try:
        success, answer = await co.switch(query)
    except Exception as e:
        raise
    if success:
        if isinstance(answer, Answer):
            return True, answer
        else:
            raise RuntimeError('Unexpected msg type')
    else:
        return False, None


async def make_answer(response: str, q: Question, to: Pairwise):
    answer = Answer(
        response=response,
        thread_id=q.id
    )
    answer.set_out_time()
    await sirius_sdk.send_to(answer, to)
