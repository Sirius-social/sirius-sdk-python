from typing import List

import sirius_sdk


async def schedule_vaults(p2p: sirius_sdk.Pairwise, vaults: List[sirius_sdk.aries_rfc.EncryptedDataVault]):
    co = await sirius_sdk.spawn_coprotocol()
    await co.subscribe_ext(
        sender_vk=[p2p.their.verkey],
        recipient_vk=[p2p.me.verkey],
        protocols=[sirius_sdk.aries_rfc.BaseConfidentialStorageMessage.PROTOCOL]
    )
    protocol = sirius_sdk.aries_rfc.CalledEncryptedDataVault(caller=p2p, proxy_to=vaults)
    try:
        while True:
            e = await co.get_message()
            await protocol.handle(e.message)
    finally:
        await co.abort()
