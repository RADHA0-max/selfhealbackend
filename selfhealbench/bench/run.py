"""Safe benchmark runner. Default replay never injects faults or contacts Docker."""
import argparse
import json
import os
import time
from pathlib import Path

from selfhealbench.bench.agents import DeterministicAgent, DirectLLMAgent
from selfhealbench.bench.pilot import NanoClawAgent, prepare_evidence, validate
from selfhealbench.bench.scoring import summarize

ROOT = Path(__file__).resolve().parents[1]


def load_scenarios(path=ROOT / "scenarios/pilot.json"):
    scenarios = json.loads(Path(path).read_text())
    if not isinstance(scenarios, list) or len(scenarios) != 10:
        raise ValueError("the pilot requires exactly ten scenarios")
    if {s["id"] for s in scenarios} != {"SHB-%03d" % n for n in range(1, 11)}:
        raise ValueError("invalid or duplicate scenario IDs")
    for s in scenarios:
        validate({"root_cause": s["expected_root"], "target": s["expected_root"],
                  "action": s["expected_action"], "reason": "scenario contract"})
        if s["fault"] not in ("none", "error", "latency", "stop"):
            raise ValueError("unsupported fault")
    return scenarios


def replay(scenarios, records, agent=None):
    evaluated = {}
    for scenario in scenarios:
        source = records.get(scenario["id"])
        if source is None:
            continue
        result = {"status": "ok"}
        started = time.monotonic()
        try:
            # Only allowlisted BEFORE telemetry crosses the agent boundary.
            evidence = prepare_evidence(source["before"])
            result["plan"] = validate(agent.diagnose(evidence) if agent else source["plan"])
        except TimeoutError:
            result["status"] = "timeout"
        except (ValueError, KeyError, TypeError):
            result["status"] = "invalid_decision"
        except Exception:
            result["status"] = "agent_error"
        result["planning_seconds"] = time.monotonic() - started if agent else None
        evaluated[scenario["id"]] = result
    return summarize(scenarios, evaluated)


def make_agent(args):
    if args.agent == "recorded":
        return None
    if args.agent == "deterministic":
        return DeterministicAgent()
    if not args.approved_inference:
        raise ValueError("new inference approval required; the one-shot diagnostic approval is not reusable")
    if args.agent == "llm":
        if not args.llm_url or not args.model:
            raise ValueError("explicit LLM URL and model required")
        return DirectLLMAgent(args.llm_url, args.model,
                              os.environ.get("LITELLM_API_KEY", ""), approved=True)
    from integration.nanoclaw_diagnostic_transport import NanoClawDiagnosticTransport
    if not all((args.nanoclaw_root, args.rpc_in, args.rpc_out, args.model)):
        raise ValueError("explicit NanoClaw root, queues and model required")
    return NanoClawAgent(NanoClawDiagnosticTransport(
        args.nanoclaw_root, args.rpc_in, args.rpc_out, args.model, approved=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("deterministic", "llm", "nanoclaw", "recorded"),
                        default="deterministic")
    parser.add_argument("--mode", choices=("replay", "live"), default="replay")
    parser.add_argument("--records", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only")
    parser.add_argument("--approved-inference", action="store_true")
    parser.add_argument("--llm-url")
    parser.add_argument("--model")
    parser.add_argument("--nanoclaw-root", type=Path)
    parser.add_argument("--rpc-in", type=Path)
    parser.add_argument("--rpc-out", type=Path)
    parser.add_argument("--approvals", type=Path)
    parser.add_argument("--inject", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output already exists")
    scenarios = load_scenarios()
    if args.only:
        scenarios = [s for s in scenarios if s["id"] == args.only]
        if not scenarios:
            parser.error("unknown scenario ID")
    if args.mode == "replay":
        if args.inject or args.execute:
            parser.error("replay prohibits injection and recovery")
        if not args.records:
            parser.error("replay requires recorded evidence")
        report = replay(scenarios, json.loads(args.records.read_text()), make_agent(args))
    else:
        if not (args.approvals and args.inject and args.execute):
            parser.error("live mode requires separate approvals, --inject and --execute")
        if args.agent == "recorded":
            parser.error("live mode cannot use recorded decisions")
        from selfhealbench.bench.live import IsolatedBackend, run_live
        config = json.loads(args.approvals.read_text())
        backend = IsolatedBackend(config, os.environ.get("BENCH_TOKEN", ""))
        agent = make_agent(args)
        # Reserve a campaign report before any Docker inspection, fault or inference.
        with args.out.open("x") as output:
            def save(value):
                output.seek(0)
                json.dump(value, output, indent=2)
                output.write("\n")
                output.truncate()
                output.flush()
            save({"mode": "live", "status": "starting", "requested": len(scenarios)})
            try:
                report = run_live(scenarios, agent, backend, checkpoint=save)
                save(report)
            except Exception as exc:
                save({"mode": "live", "status": "preflight_failed",
                      "requested": len(scenarios), "error_type": type(exc).__name__})
                raise
        print(json.dumps({k: report[k] for k in ("mode", "requested", "completed", "scores")}, indent=2))
        return
    with args.out.open("x") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({k: report[k] for k in ("mode", "requested", "completed", "scores")}, indent=2))


if __name__ == "__main__":
    main()
