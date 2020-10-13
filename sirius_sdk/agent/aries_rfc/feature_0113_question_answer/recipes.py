import uuid

import sirius_sdk
from sirius_sdk.errors.exceptions import SiriusTimeoutIO
from sirius_sdk.hub import CoProtocolThreaded
from sirius_sdk.agent.pairwise import Pairwise

from .messages import Question, Answer


async def ask_and_wait_answer(query: Question, to: Pairwise) -> Answer:
    co = CoProtocolThreaded(
        thid=query.id,
        to=to,
        protocols=[Question.PROTOCOL]
    )
    success, answer = await co.switch(query)
    if success:
        if isinstance(answer, Answer):
            return answer
        else:
            raise RuntimeError('Unexpected msg type')
    else:
        raise SiriusTimeoutIO('Operation terminated by timeout')


async def make_answer(response: str, q: Question, to: Pairwise):
    answer = Answer(
        response=response,
        thread_id=q.id
    )
    answer.set_out_time()
    await sirius_sdk.send_to(answer, to)
