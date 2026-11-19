"""Full-workload verification policy tests."""

import unittest

from experiments.verify_traffic_final import verify
from experiments.traffic_evidence_p15 import TrafficEvidenceError


class WorkloadPolicyTests(unittest.TestCase):
    def setUp(self):
        from experiments.tests.test_verify_traffic_final import VerifyTrafficTests
        self.fixture = VerifyTrafficTests(methodName="test_1200_request_end_to_end")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    @property
    def k6(self):
        return self.fixture.k6

    @property
    def envoy(self):
        return self.fixture.envoy

    @property
    def run_id(self):
        return self.fixture.run_id

    def write_fixture(self, *args, **kwargs):
        return self.fixture.write_fixture(*args, **kwargs)

    def test_complete_workload_accepted(self):
        self.write_fixture(count=1200)
        result = verify(
            str(self.k6),
            str(self.envoy),
            self.run_id,
            require_complete=True,
        )
        self.assertEqual(result["workload_status"], "COMPLETE")
        self.assertTrue(result["scheduled_iterations_complete"])

    def test_partial_workload_rejected_by_strict_policy(self):
        self.write_fixture(count=20)
        with self.assertRaises(TrafficEvidenceError):
            verify(
                str(self.k6),
                str(self.envoy),
                self.run_id,
                require_complete=True,
            )

    def test_partial_workload_allowed_explicitly(self):
        self.write_fixture(count=20)
        result = verify(
            str(self.k6),
            str(self.envoy),
            self.run_id,
            require_complete=False,
        )
        self.assertEqual(result["workload_status"], "PARTIAL")
        self.assertEqual(result["missing_scheduled_iterations"], 1180)
        self.assertFalse(result["scheduled_iterations_complete"])


if __name__ == "__main__":
    unittest.main()
