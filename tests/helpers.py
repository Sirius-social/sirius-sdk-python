import os
import asyncio
from urllib.parse import urljoin

import aiohttp
import pytest

from sirius_sdk.base import ReadOnlyChannel, WriteOnlyChannel
from sirius_sdk.errors.exceptions import SiriusTimeoutIO
from sirius_sdk.encryption import P2PConnection


class ServerTestSuite:

    SETUP_TIMEOUT = 60

    def __init__(self):
        self.__server_address = pytest.test_suite_baseurl
        self.__url = urljoin(self.__server_address, '/test_suite')
        self.__metadata = None
        test_suite_path = os.getenv('TEST_SUITE', None)
        self.__test_suite_exists_locally = os.path.isfile(test_suite_path) and 'localhost' in self.__server_address

    @property
    def metadata(self):
        return self.__metadata
    
    def get_agent_params(self, name: str):
        if not self.__metadata:
            raise RuntimeError('TestSuite is not running...')
        agent = self.__metadata.get(name, None)
        if not agent:
            raise RuntimeError('TestSuite does not have agent with name "%s"' % name)
        p2p = agent['p2p']
        return {
            'server_address': self.__server_address,
            'credentials': agent['credentials'].encode('ascii'),
            'p2p': P2PConnection(
                my_keys=(
                    p2p['smart_contract']['verkey'],
                    p2p['smart_contract']['secret_key']
                ),
                their_verkey=p2p['agent']['verkey']
            ),
            'entities': agent['entities']
        }

    async def ensure_is_alive(self):
        ok, meta = await self.__http_get(self.__url)
        if ok:
            self.__metadata = meta
        else:
            if self.__test_suite_exists_locally:
                await self.__run_suite_locally()
            inc_timeout = 10
            print('\n\nStarting test suite locally...\n\n')

            for n in range(1, self.SETUP_TIMEOUT, inc_timeout):
                progress = float(n / self.SETUP_TIMEOUT)*100
                print('Progress: %.1f %%' % progress)
                await asyncio.sleep(inc_timeout)
                ok, meta = await self.__http_get(self.__url)
                if ok:
                    self.__metadata = meta
                    print('Server test suite was detected')
                    return
            print('Timeout for waiting TestSuite is alive expired!')
            raise RuntimeError('Expect server with running TestSuite. See conftest.py: pytest_configure')

    @staticmethod
    async def __run_suite_locally():
        os.popen('python /app/configure.py --asgi_port=$ASGI_PORT --wsgi_port=$WSGI_PORT --nginx_port=$PORT')
        await asyncio.sleep(1)
        os.popen('python /app/manage.py test_suite > /tmp/test_suite.log 2> /tmp/test_suite.err')
        os.popen('supervisord -c /etc/supervisord.conf & sudo nginx -g "daemon off;"')
        await asyncio.sleep(5)

    @staticmethod
    async def __http_get(url: str):
        async with aiohttp.ClientSession() as session:
            headers = {
                'content-type': 'application/json'
            }
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status in [200]:
                        content = await resp.json()
                        return True, content
                    else:
                        err_message = await resp.text()
                        return False, err_message
            except aiohttp.ClientError:
                return False, None


class InMemoryChannel(ReadOnlyChannel, WriteOnlyChannel):

    def __init__(self):
        self.queue = asyncio.Queue()

    async def read(self, timeout: int = None) -> bytes:

        ret = None

        async def internal_reading():
            nonlocal ret
            ret = await self.queue.get()
            print('!')

        done, pending = await asyncio.wait([internal_reading()], timeout=timeout)

        for coro in pending:
            coro.cancel()
        if isinstance(ret, bytes):
            return ret
        else:
            raise SiriusTimeoutIO()

    async def write(self, data: bytes) -> bool:
        await self.queue.put(data)
        return True


async def run_coroutines(*args):
    items = [i for i in args]
    done, pending = await asyncio.wait(items, timeout=15, return_when=asyncio.FIRST_EXCEPTION)
    for f in done:
        if f.exception():
            raise f.exception()
    for f in pending:
        f.cancel()