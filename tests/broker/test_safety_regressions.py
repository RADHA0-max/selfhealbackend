import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from broker.protocol import parse_request
from broker.litellm_client import LiteLLMClient
from broker.main import Broker


def request_raw(**updates):
    value = dict(request_id='test-id', model='fast', messages=[dict(role='user', content='fixture')])
    value.update(updates)
    return json.dumps(value).encode()


@pytest.mark.parametrize('identity', ['../escape', 'a/b', 'a\\b', '.', 'x'*129])
def test_request_id_cannot_escape_queue(identity):
    with pytest.raises(ValueError):
        parse_request(request_raw(request_id=identity))


def test_duplicate_request_keys_rejected():
    with pytest.raises(ValueError, match='duplicate'):
        parse_request(request_raw().replace(b'"model": "fast"', b'"model":"deep","model":"fast"'))


@pytest.mark.parametrize('raw', [b'{}', b'not json', b'x'*65537,
                               b'{"choices":[],"choices":[]}',
                               b'{"choices":[{"message":{"content":42}}]}'])
def test_backend_malformed_responses_are_sanitized(raw, caplog):
    class Response:
        status = 200
        @property
        def content(self): return self
        async def iter_chunked(self, size): yield raw
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    class Session:
        def post(self, *args, **kwargs):
            assert kwargs['allow_redirects'] is False
            assert kwargs['timeout'].total == 30
            return Response()
    client = LiteLLMClient(SimpleNamespace(litellm_base_url='http://litellm:4000', litellm_master_key='fixture-secret'))
    client.session = Session()
    response = json.loads(asyncio.run(client.call_litellm(parse_request(request_raw()))))
    assert response['ok'] is False
    assert response['error'] == 'inference backend failed'
    assert 'fixture-secret' not in caplog.text


def test_timeout_has_explicit_safe_error():
    class Session:
        def post(self, *args, **kwargs): raise asyncio.TimeoutError('private upstream details')
    client = LiteLLMClient(SimpleNamespace(litellm_base_url='http://litellm:4000', litellm_master_key='fixture'))
    client.session = Session()
    response = json.loads(asyncio.run(client.call_litellm(parse_request(request_raw()))))
    assert response['error'] == 'inference timeout'


def test_duplicate_does_not_call_inference(tmp_path):
    config = SimpleNamespace(**{'rpc_'+name+'_dir': str(tmp_path/name) for name in ('in','out','failed')}, max_queue_size=8)
    with patch('broker.main.load_config', return_value=config): broker = Broker()
    (tmp_path/'in/req-test-id.json').write_bytes(request_raw())
    (tmp_path/'out/resp-test-id.json').write_text('original')
    broker._process_request_with_litellm = AsyncMock()
    asyncio.run(broker._process_requests())
    broker._process_request_with_litellm.assert_not_called()
    assert (tmp_path/'out/resp-test-id.json').read_text() == 'original'
