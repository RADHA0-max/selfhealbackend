"""Read-only integrity report combining incident reconciliation and receipts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.incident_reconciliation_p13 import reconcile_offline_incidents
from agent.measured_audit_p12 import audit_measured_receipts


def report_incident_integrity(
    output_dir: str | Path,
    *,
    evidence_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Reconcile durable state and verify receipts without replaying work."""

    incidents = reconcile_offline_incidents(output_dir)
    receipts = audit_measured_receipts(
        output_dir,
        evidence_dir=evidence_dir,
    )

    if receipts["receipts_verified"] > incidents["completed"]:
        raise ValueError("verified receipts exceed completed incidents")

    return {
        "report_version": 1,
        "mode": "read_only_incident_integrity",
        "incidents": incidents,
        "measured_receipts": receipts,
        "requires_manual_review": incidents["unresolved"] > 0,
        "automatic_replay_allowed": False,
        "mitigation_executed": False,
        "recovery_attributed_to_agent": False,
        "production_recovery_verified": False,
    }
