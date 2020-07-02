from typing import List

from ....messaging import Message, validate_common_blocks
from ..base import AbstractStateMachine
from .messages import ARIES_PROTOCOL


class Inviter(AbstractStateMachine):

    @property
    def protocols(self) -> List[str]:
        return [ARIES_PROTOCOL]

    async def begin(self):
        await super().begin()


class Invitee(AbstractStateMachine):

    @property
    def protocols(self) -> List[str]:
        return [ARIES_PROTOCOL]
