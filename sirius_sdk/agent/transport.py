import aiohttp


async def http_send(msg: bytes, endpoint: str, content_type: str='application/ssi-agent-wire'):
    """Send over HTTP"""
    async with aiohttp.ClientSession() as session:
        headers = {'content-type': content_type}
        async with session.post(endpoint, data=msg, headers=headers) as resp:
            body = await resp.read()
            if resp.status in [200, 202]:
                return True, body
            else:
                return False, body
