"""No-tool NanoClaw provider subprocess; explicit queue paths and approval required.

This uses NanoClaw's real BrokerProvider. It never calls LiteLLM directly and
never sends messages to the daemon, whose routing may wake containers.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from integration.nanoclaw_transport import NanoClawTransportError


class NanoClawDiagnosticTimeout(NanoClawTransportError, TimeoutError):
    pass


class NanoClawDiagnosticTransport:
    def __init__(self, root, rpc_in, rpc_out, model='fast', timeout=30,
                 approved=False):
        if not approved:
            raise ValueError('Explicit operator approval required for inference queue submission')
        if type(timeout) not in (float, int) or not math.isfinite(timeout) or not 0 < timeout <= 120:
            raise ValueError('Timeout must be within (0, 120] seconds')
        if model not in ('fast', 'plan', 'deep', 'coder'):
            raise ValueError('Unsupported NanoClaw model alias')
        self.root = Path(root).resolve()
        self.rpc_in, self.rpc_out = Path(rpc_in).resolve(), Path(rpc_out).resolve()
        if not self.rpc_in.is_dir() or not self.rpc_out.is_dir():
            raise ValueError('Existing explicit RPC directories required')
        node = shutil.which('node')
        if not node:
            raise ValueError('Node runtime unavailable')
        self.command = [node, '--import', str(self.root / 'node_modules/tsx/dist/loader.mjs'),
                        str(self.root / 'container/agent-runner/src/diagnostic.ts'),
                        str(self.rpc_in), str(self.rpc_out), model, str(int(timeout * 1000))]
        self.timeout = timeout
        self.last_trace = None

    def request(self, prompt):
        self.last_trace = None
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('Nonempty diagnostic prompt required')
        request_id = 'diag-' + uuid.uuid4().hex
        payload = json.dumps({'request_id': request_id, 'prompt': prompt}).encode()
        if len(payload) > 60 * 1024:
            raise ValueError('Diagnostic input exceeds 60 KiB')
        # File capture avoids unbounded in-memory stdout/stderr buffering.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            try:
                result = subprocess.run(self.command, input=payload, stdout=output,
                                        stderr=errors, timeout=self.timeout + 5, check=False)
            except subprocess.TimeoutExpired as exc:
                raise NanoClawDiagnosticTimeout('Diagnostic process timed out') from exc
            except OSError as exc:
                raise NanoClawTransportError('Diagnostic process failed or timed out') from exc
            if result.returncode == 124:
                raise NanoClawDiagnosticTimeout('Broker inference timed out')
            if result.returncode:
                raise NanoClawTransportError('Diagnostic inference failed')
            output.seek(0)
            raw = output.read(64 * 1024 + 1)
        if len(raw) > 64 * 1024:
            raise NanoClawTransportError('Diagnostic response exceeds 64 KiB')
        try:
            response = json.loads(raw)
            if set(response) != {'request_id', 'rpc_request_id', 'diagnosis'}:
                raise ValueError('Invalid fields')
            if response['request_id'] != request_id:
                raise ValueError('Mismatched diagnostic request ID')
            import re
            if not isinstance(response['rpc_request_id'], str) or not re.fullmatch(r'req-[a-f0-9-]{36}', response['rpc_request_id']):
                raise ValueError('Invalid file-RPC ID')
            if not isinstance(response['diagnosis'], str):
                raise ValueError('Raw diagnosis JSON required')
            def unique_fields(pairs):
                parsed = {}
                for key, value in pairs:
                    if key in parsed:
                        raise ValueError('Duplicate diagnosis field')
                    parsed[key] = value
                return parsed
            from selfhealbench.bench.pilot import validate
            diagnosis = validate(json.loads(response['diagnosis'], object_pairs_hook=unique_fields))
        except (ValueError, TypeError, KeyError) as exc:
            raise NanoClawTransportError('Invalid correlated diagnostic response') from exc
        self.last_trace = {'request_id': request_id, 'rpc_request_id': response['rpc_request_id']}
        return json.dumps(diagnosis)
