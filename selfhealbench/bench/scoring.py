"""Score every requested scenario, including missing and failed runs."""
import math

from selfhealbench.bench.pilot import validate, healthy
from selfhealbench.bench.telemetry import complete_evidence, error_rate_verified


def verified_history(value):
    if not isinstance(value, dict) or value.get("recovered") is not True:
        return False
    history = value.get("history")
    if not isinstance(history, list) or len(history) < 3:
        return False
    previous = -1
    for sample in history:
        if not isinstance(sample, dict):
            return False
        elapsed = sample.get("elapsed_seconds")
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0 or elapsed <= previous or elapsed >= 20:
            return False
        if type(sample.get("ok")) is not bool or sample["ok"] != healthy(sample.get("probes")):
            return False
        previous = elapsed
    return (all(sample.get("ok") is True for sample in history[-3:])
            and all(b["elapsed_seconds"] - a["elapsed_seconds"] >= 2
                    for a, b in zip(history[-3:], history[-2:])))


def summarize(scenarios, records, mode="offline_replay"):
    rows = []
    live = mode == "live"
    for scenario in scenarios:
        record = records.get(scenario["id"])
        row = {"scenario_id": scenario["id"], "status": "missing",
               "rca_correct": False, "target_correct": False, "action_correct": False,
               "recovery_success": False if live else None,
               "unnecessary_intervention": None, "planning_seconds": None,
               "recovery_seconds": None, "agent_to_recovery_seconds": None,
               "evidence_complete": False, "telemetry_failures": 0}
        if record is not None:
            if not isinstance(record, dict):
                record = {"status": "invalid_decision"}
            before = record.get("before", {})
            row["evidence_complete"] = complete_evidence(before)
            errors = before.get("collection_errors", []) if isinstance(before, dict) else []
            row["telemetry_failures"] = len(errors) if isinstance(errors, list) else 1
            row["status"] = record.get("status", "invalid_decision")
            try:
                plan = validate(record.get("plan"))
                # A plan left over from a failed run cannot rescue that run's score.
                if row["status"] == "ok":
                    row.update(rca_correct=plan["root_cause"] == scenario["expected_root"],
                               target_correct=plan["target"] == scenario["expected_root"],
                               action_correct=plan["action"] == scenario["expected_action"])
                row["unnecessary_intervention"] = (
                    scenario["fault"] == "none" and plan["action"] not in ("no_op", "escalate"))
                row["plan"] = plan
            except (ValueError, TypeError):
                if row["status"] == "ok":
                    row["status"] = "invalid_decision"
            # Never treat a plan, success HTTP control response, or replay as recovery.
            if live and row["status"] == "ok":
                row["recovery_success"] = (record.get("baseline_verified") is True
                                           and record.get("injection_ok") is True
                                           and (scenario["fault"] == "none"
                                                or record.get("fault_observed") is True)
                                           and record.get("recovery_verified") is True
                                           and row["evidence_complete"]
                                           and verified_history(record.get("baseline"))
                                           and verified_history(record.get("verification"))
                                           and (record.get("cleanup") == "verified"
                                                if scenario["fault"] != "none"
                                                else plan["action"] == "no_op")
                                           and record.get("rollback") not in ("failed", "required")
                                           and ("error_rate" not in record or error_rate_verified(record["error_rate"])))
            for name in ("planning_seconds", "recovery_seconds", "agent_to_recovery_seconds"):
                value = record.get(name)
                if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                    if name == "planning_seconds" or row["recovery_success"]:
                        row[name] = value
        rows.append(row)
    denominator = len(scenarios)
    benign = [r for s, r in zip(scenarios, rows) if s["fault"] == "none"]
    latencies = {}
    for name in ("planning_seconds", "recovery_seconds", "agent_to_recovery_seconds"):
        values = [r[name] for r in rows if r[name] is not None]
        latencies[name] = {"observations": len(values),
                           "mean": sum(values) / len(values) if values else None}
    return {
        "mode": mode, "requested": denominator,
        "attempted": sum(r["status"] != "missing" for r in rows),
        "skipped": sum(r["status"] == "missing" for r in rows),
        "evidence_completeness": {"complete": sum(r["evidence_complete"] for r in rows), "requested": denominator},
        "telemetry_failures": sum(r["telemetry_failures"] for r in rows),
        "completed": sum(r["status"] == "ok" for r in rows),
        "missing_scenarios": [r["scenario_id"] for r in rows if r["status"] == "missing"],
        "invalid_decisions": sum(r["status"] == "invalid_decision" for r in rows),
        "timeouts": sum(r["status"] == "timeout" for r in rows),
        "failures": sum(r["status"] not in ("ok", "missing") for r in rows),
        "scores": {name: sum(r[name] for r in rows) / denominator if denominator else None
                   for name in ("rca_correct", "target_correct", "action_correct")},
        "recovery_success": (sum(r["recovery_success"] for r in rows) / denominator
                             if live and denominator else None),
        "unnecessary_intervention": {
            "count": sum(r["unnecessary_intervention"] is True for r in benign),
            "benign_requested": len(benign),
            "rate": (sum(r["unnecessary_intervention"] is True for r in benign) / len(benign)
                     if benign and all(r["unnecessary_intervention"] is not None for r in benign) else None),
            "unknown": sum(r["unnecessary_intervention"] is None for r in benign)},
        "latencies": latencies, "results": rows,
        "denominator_note": "All requested cases remain in accuracy and live recovery denominators.",
    }
