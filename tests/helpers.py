import os
import json
import asyncio
from urllib.parse import urljoin, urlparse

import aiohttp
import pytest

from sirius_sdk.base import ReadOnlyChannel, WriteOnlyChannel
from sirius_sdk.errors.exceptions import SiriusTimeoutIO
from sirius_sdk.encryption import P2PConnection


class IndyAgent:

    WALLET = 'test'
    PASS_PHRASE = 'pass'
    DEFAULT_LABEL = 'BackCompatibility'
    SETUP_TIMEOUT = 60

    def __init__(self):
        self.__address = pytest.old_agent_address
        self.__auth_username = pytest.old_agent_root['username']
        self.__auth_password = pytest.old_agent_root['password']
        self.__endpoint = None
        self.__wallet_exists = False
        self.__endpoint = None
        self.__default_invitation = None

    @property
    def endpoint(self) -> str:
        return self.__endpoint

    @property
    def default_invitation(self) -> dict:
        return self.__default_invitation

    async def invite(self, invitation_url: str, for_did: str=None, ttl: int=None):
        url = '/agent/admin/wallets/%s/endpoints/%s/invite/' % (self.WALLET, self.endpoint['uid'])
        params = {'url': invitation_url, 'pass_phrase': self.PASS_PHRASE}
        if for_did:
            params['my_did'] = for_did
        if ttl:
            params['ttl'] = ttl
        ok, resp = await self.__http_post(
            path=url,
            json_=params
        )
        assert ok

    async def load_invitations(self):
        url = '/agent/admin/wallets/%s/endpoints/%s/invitations/' % (self.WALLET, self.__endpoint['uid'])
        ok, collection = await self.__http_get(url)
        assert ok is True
        return collection

    async def create_invitation(self, label: str, seed: str=None):
        url = '/agent/admin/wallets/%s/endpoints/%s/invitations/' % (self.WALLET, self.__endpoint['uid'])
        params = {'label': label, 'pass_phrase': self.PASS_PHRASE}
        if seed:
            params['seed'] = seed
        ok, invitation = await self.__http_post(url, params)
        assert ok is True
        return invitation

    async def ensure_is_alive(self):
        inc_timeout = 10
        for n in range(1, self.SETUP_TIMEOUT, inc_timeout):
            ok, wallets = await self.__http_get('/agent/admin/wallets/')
            if ok:
                break
            progress = float(n / self.SETUP_TIMEOUT) * 100
            print('Indy-Agent setup Progress: %.1f %%' % progress)
            await asyncio.sleep(inc_timeout)
        if not self.__wallet_exists:
            ok, wallets = await self.__http_post(
                '/agent/admin/wallets/ensure_exists/',
                {'uid': self.WALLET, 'pass_phrase': self.PASS_PHRASE}
            )
            assert ok is True
            self.__wallet_exists = True
        ok, resp = await self.__http_post(
            '/agent/admin/wallets/%s/open/' % self.WALLET,
            {'pass_phrase': self.PASS_PHRASE}
        )
        assert ok
        if not self.__endpoint:
            url = '/agent/admin/wallets/%s/endpoints/' % self.WALLET
            ok, resp = await self.__http_get(url)
            assert ok is True
            if resp['results']:
                self.__endpoint = resp['results'][0]
            else:
                ok, endpoint = ok, wallets = await self.__http_post(url, {'host': self.__address})
                assert ok is True
                self.__endpoint = endpoint
        if not self.__default_invitation:
            url = '/agent/admin/wallets/%s/endpoints/%s/invitations/' % (self.WALLET, self.__endpoint['uid'])
            ok, resp = await self.__http_get(url)
            assert ok is True
            collection = [item for item in resp if item['seed'] == 'default']
            if collection:
                self.__default_invitation = collection[0]
            else:
                ok, invitaion = ok, wallets = await self.__http_post(
                    url,
                    {'label': self.DEFAULT_LABEL, 'pass_phrase': self.PASS_PHRASE, 'seed': 'default'}
                )
                assert ok is True
                self.__default_invitation = invitaion
        print('!')

    async def __http_get(self, path: str):
        url = urljoin(self.__address, path)
        auth = aiohttp.BasicAuth(self.__auth_username, self.__auth_password, 'utf-8')
        netloc = urlparse(self.__address).netloc
        host = netloc.split(':')[0]
        async with aiohttp.ClientSession(auth=auth) as session:
            headers = {
                'content-type': 'application/json',
                'host': host
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

    async def __http_post(self, path: str, json_: dict=None):
        url = urljoin(self.__address, path)
        auth = aiohttp.BasicAuth(self.__auth_username, self.__auth_password, 'utf-8')
        netloc = urlparse(self.__address).netloc
        host = netloc.split(':')[0]
        async with aiohttp.ClientSession(auth=auth) as session:
            headers = {
                'content-type': 'application/json',
                'host': host
            }
            try:
                body = json.dumps(json_).encode() if json_ else None
                async with session.post(url, headers=headers, data=body) as resp:
                    if resp.status in [200, 201]:
                        try:
                            content = await resp.json()
                        except Exception as e:
                            content = None
                        return True, content
                    else:
                        err_message = await resp.text()
                        return False, err_message
            except aiohttp.ClientError:
                return False, None


class ServerTestSuite:

    SETUP_TIMEOUT = 60

    def __init__(self):
        self.__server_address = pytest.test_suite_baseurl
        self.__url = urljoin(self.__server_address, '/test_suite')
        self.__metadata = None
        test_suite_path = os.getenv('TEST_SUITE', None)
        if test_suite_path is None:
            self.__test_suite_exists_locally = False
        else:
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
                print('TestSuite setup progress: %.1f %%' % progress)
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
