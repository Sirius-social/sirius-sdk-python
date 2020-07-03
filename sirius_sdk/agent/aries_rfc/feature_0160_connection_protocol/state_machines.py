from typing import List

from ....messaging import Message, validate_common_blocks
from ..base import AbstractStateMachine


class Inviter(AbstractStateMachine):

    @property
    def protocols(self) -> List[str]:
        return []

    async def begin(self):
        await super().begin()


class Invitee(AbstractStateMachine):

    @property
    def protocols(self) -> List[str]:
        return []
