"""Summarize immutable offline incident records without claiming recovery."""

import json
from pathlib import Path


class IncidentReportError(ValueError):
    pass


def summarize_offline_incidents(output_dir):
    """Read bounded offline incident records; never invoke the model."""
    directory = Path(output_dir) / "offline_incidents"

    report = {
        "report_version": 1,
        "mode": "synthetic_offline_observation",
        "attempted": 0,
        "completed": 0,
        "unresolved": 0,
        "observed_success": 0,
        "observed_failure": 0,
        "inconclusive": 0,
        "production_recovery_verified": False,
    }

    if not directory.exists():
        return report

    if not directory.is_dir():
        raise IncidentReportError("incident record path is not a directory")

    intents = set()
    completed = {}

    for path in directory.glob("run-offline-incident-*.json"):
        if path.is_symlink() or not path.is_file():
            raise IncidentReportError("invalid incident record file")

        if path.stat().st_size > 1024 * 1024:
            raise IncidentReportError("incident record exceeds size limit")

        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError, OSError) as exc:
            raise IncidentReportError("invalid incident record") from exc

        if not isinstance(record, dict):
            raise IncidentReportError("invalid incident record object")

        run_id = record.get("run_id")
        if not isinstance(run_id, str):
            raise IncidentReportError("missing incident run ID")

        if record.get("record_type") == "offline_incident_intent":
            intents.add(run_id)
        elif record.get("record_type") == "offline_incident_observation":
            if run_id in completed:
                raise IncidentReportError("duplicate completed incident")
            completed[run_id] = record
        else:
            raise IncidentReportError("unsupported incident record type")

    if not set(completed).issubset(intents):
        raise IncidentReportError("completed incident missing intent")

    report["attempted"] = len(intents)
    report["completed"] = len(completed)
    report["unresolved"] = len(intents - set(completed))

    for record in completed.values():
        result = record.get("result")
        if not isinstance(result, dict):
            raise IncidentReportError("invalid incident result")

        if record.get("production_recovery_verified") is not False:
            raise IncidentReportError("unsupported recovery verification claim")

        if result.get("mitigation_executed") is not False:
            raise IncidentReportError("unsupported mitigation claim")

        if result.get("recovery_attributed_to_agent") is not False:
            raise IncidentReportError("unsupported recovery attribution")

        outcome = result.get("observation_outcome")

        if outcome == "SUCCESS":
            report["observed_success"] += 1
        elif outcome == "FAILED":
            report["observed_failure"] += 1
        elif outcome == "INCONCLUSIVE":
            report["inconclusive"] += 1
        else:
            raise IncidentReportError("unsupported observation outcome")

    return report
