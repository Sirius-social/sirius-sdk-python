import os
import json
import base64
import asyncio
import datetime
import hashlib
from typing import List, Any, Optional
from contextlib import asynccontextmanager
from urllib.parse import urljoin, urlparse

import aiohttp
import pytest
import sirius_sdk

from sirius_sdk import Agent, Pairwise, APICrypto
from sirius_sdk.base import ReadOnlyChannel, WriteOnlyChannel
from sirius_sdk.agent.wallet.abstract import AbstractDID
from sirius_sdk.agent.wallet.abstract import AbstractPairwise
from sirius_sdk.errors.exceptions import SiriusTimeoutIO
from sirius_sdk.encryption import *
from sirius_sdk.agent.aries_rfc.feature_0036_issue_credential import ProposedAttrib as IssuingProposedAttrib, \
    AttribTranslation as IssuingAttribTranslation


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
    def endpoint(self) -> dict:
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

    async def create_and_store_my_did(self, seed: str = None) -> (str, str):
        url = '/agent/admin/wallets/%s/did/create_and_store_my_did/' % self.WALLET
        params = {'pass_phrase': self.PASS_PHRASE}
        if seed:
            params['seed'] = seed
        ok, resp = await self.__http_post(url, params)
        assert ok is True
        return resp['did'], resp['verkey']

    async def create_pairwise_statically(self, pw: Pairwise):
        url = '/agent/admin/wallets/%s/pairwise/create_pairwise_statically/' % self.WALLET
        metadata = {
            'label': pw.their.label,
            'their_vk': pw.their.verkey,
            'my_vk': pw.me.verkey,
            'their_endpoint': pw.their.endpoint
        }
        params = {'pass_phrase': self.PASS_PHRASE}
        params.update({
            'my_did': pw.me.did,
            'their_did': pw.their.did,
            'their_verkey': pw.their.verkey,
            'metadata': metadata
        })
        ok, resp = await self.__http_post(url, params)
        assert ok is True

    async def register_schema(self, issuer_did: str, name: str, version: str, attributes: List[str]) -> (str, dict):
        url = '/agent/admin/wallets/%s/did/%s/ledger/register_schema/' % (self.WALLET, issuer_did)
        params = {
            'pass_phrase': self.PASS_PHRASE,
            'name': name,
            'version': version,
            'attributes': attributes
        }
        ok, resp = await self.__http_post(url, params)
        assert ok is True
        return resp['schema_id'], resp['schema']

    async def register_cred_def(
            self, submitter_did: str, schema_id : str, tag: str, support_revocation: bool = False
    ):
        url = '/agent/admin/wallets/%s/did/%s/cred_def/create_and_send/' % (self.WALLET, submitter_did)
        params = {
            'pass_phrase': self.PASS_PHRASE,
            'schema_id': schema_id,
            'tag': tag,
            'support_revocation': support_revocation
        }
        ok, resp = await self.__http_post(url, params)
        assert ok is True
        return resp['id'], resp['cred_def']

    async def issue_credential(
            self, cred_def_id: str, cred_def: dict, values: dict, their_did: str,
            comment: str = None, locale: str = None, issuer_schema: dict = None,
            preview: List[IssuingProposedAttrib] = None, translation: List[IssuingAttribTranslation] = None,
            rev_reg_id: str = None, cred_id: str = None, ttl: int = 60
    ) -> Any:
        url = '/agent/admin/wallets/%s/messaging/issue_credential/' % self.WALLET
        params = {
            'pass_phrase': self.PASS_PHRASE,
            'cred_def_id': cred_def_id,
            'cred_def': cred_def,
            'values': values,
            'their_did': their_did
        }
        if comment:
            params['comment'] = comment
        if locale:
            params['locale'] = locale
        if issuer_schema:
            params['issuer_schema'] = issuer_schema
        if preview:
            params['preview'] = preview
        if translation:
            params['translation'] = translation
        if rev_reg_id:
            params['rev_reg_id'] = rev_reg_id
        if cred_id:
            params['cred_id'] = cred_id
        if ttl:
            params['ttl'] = ttl
        params['collect_log'] = True
        ok, resp = await self.__http_post(url, params)
        assert ok is True
        return resp

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

    async def __http_post(self, path: str, json_: dict = None):
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


async def run_coroutines(*args, timeout: int = 15):
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


async def ensure_cred_def_exists_in_dkms(
        network_name: str, did_issuer: str, schema_name: str, schema_ver: str, attrs: list, tag: str
) -> (sirius_sdk.Schema, sirius_sdk.CredentialDefinition):
    dkms = await sirius_sdk.dkms(network_name)  # Test network is prepared for Demo purposes
    schema_id, anon_schema = await sirius_sdk.AnonCreds.issuer_create_schema(
        did_issuer, schema_name, schema_ver, attrs
    )
    # Ensure schema exists on DKMS
    schema_ = await dkms.ensure_schema_exists(anon_schema, did_issuer)
    # Ensure CredDefs is stored to DKMS
    cred_def_fetched = await dkms.fetch_cred_defs(tag=tag, schema_id=schema_.id)
    if cred_def_fetched:
        cred_def_ = cred_def_fetched[0]
    else:
        ok, cred_def_ = await dkms.register_cred_def(
            cred_def=sirius_sdk.CredentialDefinition(tag=tag, schema=schema_),
            submitter_did=did_issuer
        )
        assert ok is True
    return schema_, cred_def_


@asynccontextmanager
async def fix_timeout(caption: str):
    stamp1 = datetime.datetime.utcnow()
    yield
    stamp2 = datetime.datetime.utcnow()
    delta = stamp2 - stamp1
    print(f'Timeout for {caption}: {delta.total_seconds()} secs, utc1: {stamp1} utc2: {stamp2}')


class LocalCryptoManager(APICrypto):

    """Crypto module on device side, for example Indy-Wallet or HSM or smth else

      - you may override this code block with Aries-Askar
    """

    def __init__(self):
        self.__keys = []

    async def create_key(self, seed: str = None, crypto_type: str = None) -> str:
        if seed:
            seed = seed.encode()
        else:
            seed = None
        vk, sk = create_keypair(seed)
        self.__keys.append([vk, sk])
        return bytes_to_b58(vk)

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        raise NotImplemented

    async def get_key_metadata(self, verkey: str) -> Optional[dict]:
        self.__check_verkey(verkey)
        return None

    async def crypto_sign(self, signer_vk: str, msg: bytes) -> bytes:
        vk, sk = self.__check_verkey(signer_vk)
        signature = sign_message(
            message=msg,
            secret=sk
        )
        return signature

    async def crypto_verify(self, signer_vk: str, msg: bytes, signature: bytes) -> bool:
        success = verify_signed_message(
            verkey=b58_to_bytes(signer_vk),
            msg=msg,
            signature=signature
        )
        return success

    async def anon_crypt(self, recipient_vk: str, msg: bytes) -> bytes:
        raise NotImplemented

    async def anon_decrypt(self, recipient_vk: str, encrypted_msg: bytes) -> bytes:
        raise NotImplemented

    async def pack_message(self, message: Any, recipient_verkeys: list, sender_verkey: str = None) -> bytes:
        vk, sk = self.__check_verkey(sender_verkey)
        if isinstance(message, dict):
            message = json.dumps(message)
        elif isinstance(message, bytes):
            message = message.decode()
        packed = pack_message(
            message=message,
            to_verkeys=recipient_verkeys,
            from_verkey=vk,
            from_sigkey=sk
        )
        return packed

    async def unpack_message(self, jwe: bytes) -> dict:
        jwe = json.loads(jwe.decode())
        protected = jwe['protected']
        payload = json.loads(base64.b64decode(protected))
        recipients = payload['recipients']
        vk, sk = None, None
        for item in recipients:
            rcp_vk = b58_to_bytes(item['header']['kid'])
            for vk_, sk_ in self.__keys:
                if rcp_vk == vk_:
                    vk, sk = vk_, sk_
                    break
        if not vk:
            raise RuntimeError('Unknown recipient keys')
        message, sender_vk, recip_vk = unpack_message(
            enc_message=jwe,
            my_verkey=vk,
            my_sigkey=sk
        )
        return {
            'message': message,
            'recipient_verkey': recip_vk,
            'sender_verkey': sender_vk
        }

    def __check_verkey(self, verkey: str) -> (bytes, bytes):
        verkey_bytes = b58_to_bytes(verkey)
        for vk, sk in self.__keys:
            if vk == verkey_bytes:
                return vk, sk
        raise RuntimeError('Unknown Verkey')


class LocalDIDManager(AbstractDID):
    """You may override this code block with Aries-Askar"""

    def __init__(self, crypto: LocalCryptoManager = None):
        self._storage = dict()
        self._crypto = crypto

    async def create_and_store_my_did(self, did: str = None, seed: str = None, cid: bool = None) -> (str, str):
        if self._crypto:
            vk = await self._crypto.create_key(seed, cid)
            did = did_from_verkey(b58_to_bytes(vk))
            return bytes_to_b58(did), vk

    async def store_their_did(self, did: str, verkey: str = None) -> None:
        descriptor = self._storage.get(did, {})
        descriptor['verkey'] = verkey
        self._storage[did] = descriptor

    async def set_did_metadata(self, did: str, metadata: dict = None) -> None:
        descriptor = self._storage.get(did, {})
        descriptor['metadata'] = metadata
        self._storage[did] = descriptor

    async def list_my_dids_with_meta(self) -> List[Any]:
        raise NotImplemented

    async def get_did_metadata(self, did) -> Optional[dict]:
        descriptor = self._storage.get(did, {})
        return descriptor.get('metadata', None)

    async def key_for_local_did(self, did: str) -> str:
        raise NotImplemented

    async def key_for_did(self, pool_name: str, did: str) -> str:
        raise NotImplemented

    async def create_key(self, seed: str = None) -> str:
        raise NotImplemented

    async def replace_keys_start(self, did: str, seed: str = None) -> str:
        raise NotImplemented

    async def replace_keys_apply(self, did: str) -> None:
        raise NotImplemented

    async def set_key_metadata(self, verkey: str, metadata: dict) -> None:
        raise NotImplemented

    async def get_key_metadata(self, verkey: str) -> dict:
        raise NotImplemented

    async def set_endpoint_for_did(self, did: str, address: str, transport_key: str) -> None:
        raise NotImplemented

    async def get_endpoint_for_did(self, pool_name: str, did: str) -> (str, Optional[str]):
        raise NotImplemented

    async def get_my_did_with_meta(self, did: str) -> Any:
        raise NotImplemented

    async def abbreviate_verkey(self, did: str, full_verkey: str) -> str:
        raise NotImplemented

    async def qualify_did(self, did: str, method: str) -> str:
        raise NotImplemented


def calc_file_hash(path: str) -> str:
    with open(path, 'rb') as f:
        raw = f.read()
    return calc_bytes_hash(raw)


def calc_file_size(path: str) -> int:
    with open(path, 'rb') as f:
        raw = f.read()
    return len(raw)


def calc_bytes_hash(raw: bytes) -> str:
    md = hashlib.md5(raw)
    return md.hexdigest()
