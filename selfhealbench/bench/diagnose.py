"""One approved, no-tool inference check. Never invokes the NanoClaw daemon."""
import argparse
import json
from pathlib import Path

from integration.nanoclaw_diagnostic_transport import NanoClawDiagnosticTransport
from selfhealbench.bench.pilot import NanoClawAgent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nanoclaw-root', required=True, type=Path)
    parser.add_argument('--rpc-in', required=True, type=Path)
    parser.add_argument('--rpc-out', required=True, type=Path)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--model', required=True, choices=('fast', 'plan', 'deep', 'coder'))
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--approved-inference-only', action='store_true')
    args = parser.parse_args()
    if not args.approved_inference_only:
        parser.error('Operator approval is required before submitting inference')
    # Read a bounded, explicitly supplied evidence file. Never read runtime secrets.
    with args.evidence.open('rb') as source:
        raw = source.read(48 * 1024 + 1)
    if len(raw) > 48 * 1024:
        parser.error('Evidence file exceeds 48 KiB')
    evidence = json.loads(raw)
    transport = NanoClawDiagnosticTransport(args.nanoclaw_root, args.rpc_in, args.rpc_out,
                                           model=args.model, timeout=args.timeout, approved=True)
    # Reserve the report BEFORE inference; a repeated command cannot spend another
    # request and only then discover that the output already exists.
    with args.out.open('x') as dest:
        report = {'mode': 'nanoclaw_provider_inference_only', 'status': 'started',
                  'live_recovery': 'not tested', 'executed_remediation': False}
        json.dump(report, dest, indent=2)
        dest.flush()
        try:
            plan = NanoClawAgent(transport).diagnose(evidence)
            report.update(status='ok', trace=transport.last_trace, plan=plan)
        except Exception as exc:
            report.update(status='timeout' if isinstance(exc, TimeoutError) else 'failed',
                          error_type=type(exc).__name__)
            raise
        finally:
            dest.seek(0)
            json.dump(report, dest, indent=2)
            dest.write('\n')
            dest.truncate()


if __name__ == '__main__':
    main()
