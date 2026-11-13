"""Offline tests for conservative diagnosis evidence gating."""

import unittest

from agent.diagnosis import Diagnosis
from agent.evidence_gate import gate_diagnosis


class EvidenceGateTests(unittest.TestCase):
    def make_diagnosis(self, category, target="api", action="investigate_api"):
        return Diagnosis(
            category=category,
            target=target,
            confidence=0.9,
            summary="Model-generated diagnosis",
            recommended_action=action,
        )

    def test_rejects_unsupported_dependency_failure(self):
        signal = {"signal_id": "case1", "target": "api", "status": 503}
        result = gate_diagnosis(
            signal,
            self.make_diagnosis("dependency_failure"),
        )
        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.recommended_action, "collect_more_evidence")
        self.assertEqual(result.confidence, 0.0)

    def test_rejects_unsupported_resource_exhaustion(self):
        signal = {"signal_id": "case2", "target": "auth", "status": 503}
        result = gate_diagnosis(
            signal,
            self.make_diagnosis("resource_exhaustion", "auth"),
        )
        self.assertEqual(result.category, "unknown")

    def test_accepts_supported_latency(self):
        signal = {
            "signal_id": "case3",
            "target": "worker",
            "status": 504,
            "latency_ms": 5000,
        }
        diagnosis = self.make_diagnosis(
            "latency", "worker", "investigate_latency"
        )
        self.assertEqual(gate_diagnosis(signal, diagnosis), diagnosis)

    def test_rejects_unsupported_latency(self):
        signal = {"signal_id": "case4", "target": "api", "status": 503}
        result = gate_diagnosis(
            signal,
            self.make_diagnosis("latency"),
        )
        self.assertEqual(result.category, "unknown")

    def test_rejects_mismatched_target(self):
        signal = {"signal_id": "case6", "target": "api", "status": 503}
        diagnosis = self.make_diagnosis(
            "service_failure", "database", "investigate_database"
        )

        result = gate_diagnosis(signal, diagnosis)

        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.target, "api")
        self.assertEqual(
            result.recommended_action,
            "collect_more_evidence",
        )

    def test_preserves_supported_service_failure(self):
        signal = {"signal_id": "case5", "target": "api", "status": 503}
        diagnosis = self.make_diagnosis("service_failure")
        self.assertEqual(gate_diagnosis(signal, diagnosis), diagnosis)


    def test_rejects_unknown_with_investigation_action(self):
        signal = {"signal_id": "case7", "target": "api", "status": 200}
        diagnosis = self.make_diagnosis("unknown")

        result = gate_diagnosis(signal, diagnosis)

        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.recommended_action, "collect_more_evidence")

    def test_rejects_cross_target_action(self):
        signal = {"signal_id": "case8", "target": "api", "status": 503}
        diagnosis = self.make_diagnosis(
            "service_failure", "api", "investigate_database"
        )

        result = gate_diagnosis(signal, diagnosis)

        self.assertEqual(result.category, "unknown")
        self.assertEqual(result.recommended_action, "collect_more_evidence")

    def test_preserves_consistent_unknown(self):
        signal = {"signal_id": "case9", "target": "api", "status": 200}
        diagnosis = self.make_diagnosis(
            "unknown", "api", "collect_more_evidence"
        )

        self.assertEqual(gate_diagnosis(signal, diagnosis), diagnosis)


if __name__ == "__main__":
    unittest.main()
