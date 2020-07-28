import re
import time
import json
import struct
import base64
from typing import List, Optional
from urllib.parse import urljoin

from ....errors.exceptions import *
from ....messaging import Message, check_for_attributes
from ....agent.agent import Agent
from ....agent.wallet.abstract.crypto import AbstractCrypto
from ....agent.aries_rfc.base import AriesProtocolMessage, RegisterMessage, AriesProblemReport, THREAD_DECORATOR
from ....agent.microledgers import Transaction


class SimpleConsensusMessage(AriesProtocolMessage, metaclass=RegisterMessage):
    """Message for Simple Consensus protocol over Microledger maintenance

    """
    PROTOCOL = 'simple-consensus'


class InitLedgerMessage(SimpleConsensusMessage):

    NAME = 'initialize'
    
    def __init__(
            self, ledger_name: Optional[str]=None, genesis: List[Transaction]=None,
            root_hash: Optional[str]=None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        if ledger_name is not None:
            self['ledger_name'] = ledger_name
        if root_hash is not None:
            self['root_hash'] = root_hash
        if genesis is not None:
            self['genesis'] = genesis
