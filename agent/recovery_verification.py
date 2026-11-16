"""Offline verification of observed service recovery; no mitigation execution."""

from agent.signal_adapter import signal_to_evidence


class VerificationError(ValueError):
    pass


def verify_recovery(before, after):
    """Return SUCCESS, FAILED, or INCONCLUSIVE from validated probe evidence."""
    initial = signal_to_evidence(before)
    final = signal_to_evidence(after)

    if before["target"] != after["target"]:
        raise VerificationError("probe targets differ")

    if before["signal_id"] == after["signal_id"]:
        raise VerificationError("verification requires a distinct observation")

    old = initial["probes"][before["target"]]
    new = final["probes"][after["target"]]

    old_status = old["status"]
    new_status = new["status"]

    if not 200 <= old_status < 400:
        if 200 <= new_status < 400:
            return "SUCCESS"
        if new_status >= 500:
            return "FAILED"
        return "INCONCLUSIVE"

    return "INCONCLUSIVE"


def verify_sustained_recovery(before, observations, required_healthy=3):
    """Validate every observation before evaluating sustained health.

    SUCCESS means observed health only, never mitigation causality.
    """
    if type(required_healthy) is not int or not 2 <= required_healthy <= 10:
        raise VerificationError("required_healthy must be an integer from 2 to 10")

    if not isinstance(observations, (list, tuple)):
        raise VerificationError("observations must be a sequence")

    if len(observations) > 10:
        raise VerificationError("too many observations")

    baseline = signal_to_evidence(before)
    target = before["target"]
    baseline_status = baseline["probes"][target]["status"]

    seen = {before["signal_id"]}
    statuses = []

    # Validate the entire sequence before returning any outcome.
    for observation in observations:
        evidence = signal_to_evidence(observation)

        if observation["target"] != target:
            raise VerificationError("observation target mismatch")

        identifier = observation["signal_id"]
        if identifier in seen:
            raise VerificationError("duplicate observation ID")

        seen.add(identifier)
        statuses.append(evidence["probes"][target]["status"])

    if 200 <= baseline_status < 400:
        return "INCONCLUSIVE"

    if any(status >= 500 for status in statuses):
        return "FAILED"

    if any(not 200 <= status < 400 for status in statuses):
        return "INCONCLUSIVE"

    if len(statuses) >= required_healthy:
        return "SUCCESS"

    return "INCONCLUSIVE"
