from typing import List

from sirius_sdk.hub import acquire, release


class Locking:

    NAMESPACE = 'ledgers'

    async def acquire(self, names: List[str], lock_timeout: float) -> (bool, List[str]):
        """Lock ledgers given by names.

        :names: names of microledgers
        :lock_timeout: lock timeout, resources will be released automatically after timeout expired
        """
        ledger_names = names[:]  # copy
        ledger_names = list(set(ledger_names))  # remove duplicates
        ledger_resources = [f'{self.NAMESPACE}/{name}' for name in ledger_names]
        ok, locked_ledgers = await acquire(resources=ledger_resources, lock_timeout=lock_timeout)
        locked_ledgers = [item.split('/')[-1] for item in locked_ledgers]  # remove namespace prefix
        return ok, locked_ledgers
        pass

    async def release(self):
        """Released all resources locked in current context"""
        await release()
        pass


__all__ = ['Locking']