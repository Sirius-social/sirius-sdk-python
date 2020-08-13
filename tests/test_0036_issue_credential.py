import uuid
from typing import List, Any
from datetime import datetime, timedelta

import pytest

from sirius_sdk import Agent, Pairwise
from sirius_sdk.agent.aries_rfc.utils import str_to_utc
from sirius_sdk.agent.ledger import Schema, CredentialDefinition
from sirius_sdk.agent.aries_rfc.feature_0036_issue_credential import Issuer, Holder, AttribTranslation, \
    ProposedAttrib, OfferCredentialMessage

from .conftest import get_pairwise
from .helpers import run_coroutines


async def run_issuer(
        agent: Agent, holder: Pairwise, values: dict, schema: Schema, cred_def: CredentialDefinition,
        preview: List[ProposedAttrib] = None, translation: List[AttribTranslation] = None, cred_id: str = None
):
    machine = Issuer(
        api=agent.wallet.anoncreds, holder=holder, comment='Hello Iam issuer', transports=agent
    )
    success = await machine.issue(
        values=values,
        schema=schema,
        cred_def=cred_def,
        preview=preview,
        translation=translation,
        cred_id=cred_id
    )
    return success


async def run_holder(agent: Agent, issuer: Pairwise, master_secret_id: str):
    listener = await agent.subscribe()
    event = await listener.get_one()
    assert event.pairwise is not None
    offer = event.message
    assert isinstance(offer, OfferCredentialMessage)
    ttl = 60
    if offer.expires_time:
        expire = str_to_utc(offer.expires_time, raise_exceptions=False)
        delta = expire - datetime.utcnow()
        if delta.seconds > 0:
            ttl = delta.seconds
    machine = Holder(
        api=agent.wallet.anoncreds, issuer=issuer, comment='Hello, Iam holder', transports=agent, time_to_live=ttl
    )
    success, cred_id = await machine.accept(offer, master_secret_id)
    return success, cred_id


@pytest.mark.asyncio
async def test_sane(agent1: Agent, agent2: Agent):
    issuer = agent1
    holder = agent2
    await issuer.open()
    await holder.open()
    try:
        i2h = await get_pairwise(issuer, holder)
        h2i = await get_pairwise(holder, issuer)

        did_issuer, verkey_issuer = i2h.me.did, i2h.me.verkey
        schema_name = 'schema_' + uuid.uuid4().hex
        schema_id, anoncred_schema = await agent1.wallet.anoncreds.issuer_create_schema(
            did_issuer, schema_name, '1.0', ['attr1', 'attr2', 'attr3']
        )
        ledger = issuer.ledger('default')
        ok, schema = await ledger.register_schema(schema=anoncred_schema, submitter_did=did_issuer)
        assert ok is True

        ok, cred_def = await ledger.register_cred_def(
            cred_def=CredentialDefinition(tag='TAG', schema=schema),
            submitter_did=did_issuer
        )
        assert ok is True
        master_secret_name = 'secret-' + uuid.uuid4().hex
        holder_secret_id = await holder.wallet.anoncreds.prover_create_master_secret(master_secret_name)

        cred_id = 'cred-id-' + uuid.uuid4().hex
        coro_issuer = run_issuer(
            agent=issuer, holder=i2h,
            values={'attr1': 'Value-1', 'attr2': 567, 'attr3': 5.7},
            schema=schema, cred_def=cred_def, cred_id=cred_id
        )
        coro_holder = run_holder(
            agent=holder,
            issuer=h2i,
            master_secret_id=holder_secret_id
        )

        results = await run_coroutines(coro_issuer, coro_holder, timeout=60)
        print(str(results))
        cred_id = None
        for res in results:
            if type(res) is tuple:
                ok, cred_id = res
            else:
                ok = res
            assert ok is True

        assert cred_id is not None
        cred = await holder.wallet.anoncreds.prover_get_credential(cred_id)
        assert cred

    finally:
        await issuer.close()
        await holder.close()
