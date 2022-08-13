import asyncio

import aiohttp


class EndpointTransport:

    def __init__(self, keepalive_timeout: float = 15):
        self.__keep_alive_connector = aiohttp.TCPConnector(
            ssl=False,  # Do not verify SSL due to all messages encrypted
            use_dns_cache=False,
            limit=0,  # No connections limit
            keepalive_timeout=keepalive_timeout
        )
        self.__websockets = {}

    def __del__(self):
        loop = asyncio.get_event_loop()
        if self.__websockets:
            if loop:
                if loop.is_running():
                    loop.create_task(self.close())
                else:
                    loop.run_until_complete(self.close())

    async def send(
            self, msg: bytes, endpoint: str, timeout: float, content_type='application/ssi-agent-wire'
    ) -> (bool, str):
        parts = endpoint.split('://')
        if len(parts) != 2:
            raise ValueError('Expected scheme in address: %s' % endpoint)
        scheme = parts[0]
        if scheme in ['http', 'https']:
            success, body = await self.http_send(msg, endpoint, timeout, content_type)
            return success, body.decode()
        elif scheme in ['ws', 'wss']:
            await self.ws_send(msg, endpoint, timeout)
            return True, ''

    async def http_send(
            self, msg: bytes, endpoint: str, timeout: float, content_type: str = 'application/ssi-agent-wire'
    ) -> (bool, bytes):
        tm = aiohttp.ClientTimeout(total=timeout)
        headers = {'content-type': content_type}
        request = aiohttp.request(
            'post', endpoint, data=msg, headers=headers, connector=self.__keep_alive_connector, timeout=tm
        )
        async with request as resp:
            body = await resp.read()
            if resp.status in [200, 202]:
                return True, body
            else:
                return False, body

    async def ws_send(self, msg: bytes, endpoint: str, timeout: float):
        tup = self.__websockets.pop(endpoint, None)
        if tup is None:
            tm = aiohttp.ClientTimeout(total=timeout)
            session = aiohttp.ClientSession(timeout=tm)
            ws = await session.ws_connect(url=endpoint)
            self.__websockets[endpoint] = (ws, session)
        else:
            ws, session = tup
            if ws.closed:
                ws = session.ws_connect(url=endpoint)
        await ws.send_bytes(msg)
        self.__websockets[endpoint] = (ws, session)

    async def close(self):
        for ws, session in self.__websockets.values():
            await ws.close()
            await session.close()


async def http_send(
        msg: bytes, endpoint: str, timeout: float,
        connector: aiohttp.TCPConnector = None,
        content_type: str = 'application/ssi-agent-wire'
):
    """Send over HTTP"""

    headers = {'content-type': content_type}
    request = aiohttp.request(
        'post', endpoint,
        data=msg,
        headers=headers,
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=timeout)
    )
    async with request as resp:
        body = await resp.read()
        if resp.status in [200, 202]:
            return True, body
        else:
            return False, body
