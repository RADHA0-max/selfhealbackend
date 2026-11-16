"""Sanitized regression patterns from the P06 real-model experiment."""

import json
import unittest

from agent.diagnosis import validate_diagnosis
from agent.evidence_gate import gate_diagnosis


class RealPilotPatternTests(unittest.TestCase):

    def test_unsupported_503_dependency_patterns(self):
        for target in ("api", "database", "auth"):
            with self.subTest(target=target):
                diagnosis = validate_diagnosis(json.dumps({
                    "category": "dependency_failure",
                    "target": target,
                    "confidence": 0.8,
                    "summary": "A dependency may have failed.",
                    "recommended_action": "investigate_" + target,
                }))

                gated = gate_diagnosis({
                    "signal_id": "p06-regression-" + target,
                    "target": target,
                    "status": 503,
                }, diagnosis)

                self.assertEqual(gated.category, "unknown")
                self.assertEqual(gated.confidence, 0.0)
                self.assertEqual(
                    gated.recommended_action,
                    "collect_more_evidence",
                )

    def test_supported_latency_pattern(self):
        diagnosis = validate_diagnosis(json.dumps({
            "category": "latency",
            "target": "worker",
            "confidence": 0.9,
            "summary": "Measured latency degradation.",
            "recommended_action": "investigate_latency",
        }))

        gated = gate_diagnosis({
            "signal_id": "p06-regression-latency",
            "target": "worker",
            "status": 504,
            "latency_ms": 5000,
        }, diagnosis)

        self.assertEqual(gated.category, "latency")
        self.assertEqual(gated.target, "worker")


if __name__ == "__main__":
    unittest.main()
