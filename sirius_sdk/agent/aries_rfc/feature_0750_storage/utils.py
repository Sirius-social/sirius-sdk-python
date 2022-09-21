import json
from typing import Optional

import sirius_sdk


PERSIST_STORAGE_TYPE = 'confidential.storage.persist'


async def update_persist_record(key: str, data: dict):
    stored = await ensure_persist_record_exists(key, data)
    if data != stored:
        await sirius_sdk.NonSecrets.update_wallet_record_value(
            type_=PERSIST_STORAGE_TYPE, id_=key, value=json.dumps(data)
        )


async def ensure_persist_record_exists(key: str, default: dict = None) -> Optional[dict]:
    if default is None:
        default = {}
    opts = sirius_sdk.NonSecretsRetrieveRecordOptions()
    opts.retrieve_value = True
    try:
        rec = await sirius_sdk.NonSecrets.get_wallet_record(
            type_=PERSIST_STORAGE_TYPE, id_=key, options=opts
        )
        states = json.loads(rec['value'])
        return states
    except:
        rec = None
    if rec is None:
        await sirius_sdk.NonSecrets.add_wallet_record(
            type_=PERSIST_STORAGE_TYPE, id_=key, value=json.dumps(default)
        )
        return default


async def ensure_persist_record_missing(key: str):
    try:
        await sirius_sdk.NonSecrets.delete_wallet_record(
            type_=PERSIST_STORAGE_TYPE, id_=key
        )
    except:
        pass
