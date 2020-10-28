import asyncio


async def join(*args, timeout: int = 30):
    results = []
    items = [i for i in args]
    done, pending = await asyncio.wait(items, timeout=timeout, return_when=asyncio.FIRST_EXCEPTION)
    for f in done:
        if f.exception():
            raise f.exception()
        results.append(f.result())
    for f in pending:
        f.cancel()
    return results

