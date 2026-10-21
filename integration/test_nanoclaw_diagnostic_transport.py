import asyncio
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from broker.main import Broker
from integration.nanoclaw_diagnostic_transport import NanoClawDiagnosticTransport
from integration.nanoclaw_transport import NanoClawTransportError
from selfhealbench.bench.pilot import NanoClawAgent

ROOT = Path(__file__).resolve().parents[1]
PLAN = {'root_cause': 'db', 'action': 'clear_fault', 'target': 'db', 'reason': 'HTTP failure'}


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        for name in ('in', 'out', 'failed'):
            (self.base/name).mkdir()

    def transport(self, **kwargs):
        return NanoClawDiagnosticTransport(ROOT/'nanoclaw', self.base/'in', self.base/'out',
                                          approved=True, **kwargs)

    def test_approval_and_size_guards(self):
        with self.assertRaises(ValueError):
            NanoClawDiagnosticTransport(ROOT/'nanoclaw', self.base/'in', self.base/'out')
        with self.assertRaises(ValueError):
            self.transport(timeout=float('nan'))
        with self.assertRaises(ValueError):
            self.transport().request('x'*65000)
        self.assertEqual(list((self.base/'in').iterdir()), [])

    def test_actual_provider_broker_client_with_mocked_http(self):
        """Real Python adapter -> TS provider -> file RPC -> real broker/client.

        Only the HTTP session at the LiteLLM boundary is fake. No network used.
        """
        observed = []
        class Response:
            status = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def json(self):
                return {'choices': [{'message': {'content':
                        '<message to="local-cli">'+json.dumps(PLAN)+'</message>'}}]}
        class Session:
            def post(inner, url, **kwargs):
                observed.append((url, kwargs['json']))
                return Response()
            async def close(self): pass
        config = SimpleNamespace(rpc_in_dir=str(self.base/'in'), rpc_out_dir=str(self.base/'out'),
                                 rpc_failed_dir=str(self.base/'failed'), max_queue_size=8,
                                 litellm_base_url='http://litellm:4000', litellm_master_key='fake-test-key')
        errors = []
        def broker_worker():
            try:
                async def work():
                    broker = Broker()
                    deadline = time.monotonic()+8
                    while time.monotonic() < deadline:
                        if list((self.base/'in').glob('req-*.json')):
                            await broker._process_requests()
                            return
                        await asyncio.sleep(.01)
                    raise AssertionError('No file-RPC request')
                asyncio.run(work())
            except Exception as exc:
                errors.append(exc)
        with patch('broker.main.load_config', return_value=config), patch('broker.litellm_client.aiohttp.ClientSession', Session):
            worker = threading.Thread(target=broker_worker)
            worker.start()
            try:
                transport = self.transport(timeout=5)
                plan = NanoClawAgent(transport, secrets=('private-token',)).diagnose({
                    'probes': {'db': {'status': 503}}, 'docker_logs': 'private-token',
                    'scenario_id': 'SHB-001', 'ground_truth': 'db'})
                self.assertEqual(plan, PLAN)
                self.assertTrue(transport.last_trace['rpc_request_id'].startswith('req-'))
            finally:
                worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(observed), 1)
        url, payload = observed[0]
        self.assertEqual(url, 'http://litellm:4000/v1/chat/completions')
        self.assertEqual(payload['model'], 'fast')
        self.assertNotIn('tools', payload)
        text = json.dumps(payload)
        for excluded in ('private-token', 'SHB-001', 'ground_truth'):
            self.assertNotIn(excluded, text)
        self.assertIn('[REDACTED]', text)

    def test_timeout_fails_closed(self):
        transport = self.transport(timeout=.2)
        with self.assertRaises(NanoClawTransportError):
            transport.request('diagnose only')
        self.assertIsNone(transport.last_trace)

    def test_duplicate_model_json_rejected(self):
        def completed(command, **kwargs):
            request = json.loads(kwargs["input"])
            kwargs["stdout"].write(json.dumps({
                "request_id": request["request_id"],
                "rpc_request_id": "req-00000000-0000-0000-0000-000000000000",
                "diagnosis": '{"root_cause":"db","action":"no_op","action":"clear_fault",'
                             '"target":"db","reason":"failure"}',
            }).encode())
            return SimpleNamespace(returncode=0)
        with patch("subprocess.run", side_effect=completed):
            with self.assertRaises(NanoClawTransportError):
                self.transport().request("diagnose only")

    def test_wrong_response_id_fails_closed(self):
        errors = []
        def respond():
            try:
                deadline = time.monotonic()+5
                while time.monotonic() < deadline:
                    files = list((self.base/'in').glob('req-*.json'))
                    if files:
                        request = json.loads(files[0].read_text())
                        (self.base/'out'/('resp-'+request['request_id']+'.json')).write_text(json.dumps({
                            'request_id': 'wrong', 'ok': True, 'content': json.dumps(PLAN)}))
                        return
                    time.sleep(.01)
            except Exception as exc:
                errors.append(exc)
        worker = threading.Thread(target=respond)
        worker.start()
        try:
            with self.assertRaises(NanoClawTransportError):
                self.transport(timeout=3).request('diagnose only')
        finally:
            worker.join(6)
        self.assertEqual(errors, [])
