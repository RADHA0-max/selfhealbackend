"""Ensure P01 workload names and request-ID markers agree."""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "testbed/experiments/p01_evidence_adapter.py"

spec = importlib.util.spec_from_file_location("p01_adapter_contract", SOURCE)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class P01ContractTests(unittest.TestCase):

    def test_all_scenarios_have_matching_request_id_marker(self):
        for marker, workload in adapter.WORKLOADS.items():
            with self.subTest(workload=workload):
                path = ROOT / "testbed/k6" / f"{workload}.js"

                self.assertTrue(path.is_file(), str(path))

                source = path.read_text(encoding="utf-8")

                # The request ID must use the marker expected by
                # the evidence adapter.
                self.assertIn(
                    f"-{marker}-vu-",
                    source,
                    f"{workload}: request ID marker mismatch",
                )

                self.assertEqual(
                    adapter.classify(
                        f"contract-{marker}-vu-1-iter-0",
                        "contract",
                    ),
                    workload,
                )


if __name__ == "__main__":
    unittest.main()
