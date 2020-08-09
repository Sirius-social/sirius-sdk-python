import aiohttp


async def http_send(
        msg: bytes, endpoint: str, timeout: float,
        connector: aiohttp.TCPConnector = None,
        content_type: str = 'application/ssi-agent-wire'
):
    """Send over HTTP"""
    headers = {'content-type': content_type}
    request = aiohttp.request('post', endpoint, data=msg, headers=headers, connector=connector)
    async with request as resp:
        body = await resp.read()
        if resp.status in [200, 202]:
            return True, body
        else:
            return False, body
