import unittest
from unittest.mock import patch, MagicMock
import time

from broker.budget import BudgetTracker


class TestBudgetTracker(unittest.TestCase):
    def setUp(self):
        self.budget_tracker = BudgetTracker()

    def test_initial_state(self):
        """Test that the budget tracker starts with correct initial state."""
        info = self.budget_tracker.get_budget_info()
        self.assertEqual(info["global_deep_requests"], 0)
        self.assertEqual(info["current_deep_coder_count"], 0)
        self.assertEqual(len(info["target_budgets"]), 0)
        self.assertEqual(len(info["active_targets"]), 0)

    def test_fast_plan_embed_requests_allowed(self):
        """Test that fast, plan, and embed requests are always allowed."""
        self.assertTrue(self.budget_tracker.can_request("fast", "target1"))
        self.assertTrue(self.budget_tracker.can_request("plan", "target1"))
        self.assertTrue(self.budget_tracker.can_request("embed", "target1"))

        # These should not affect budget tracking
        self.budget_tracker.record_request("fast", "target1")
        self.budget_tracker.record_request("plan", "target1")
        self.budget_tracker.record_request("embed", "target1")

        info = self.budget_tracker.get_budget_info()
        self.assertEqual(info["global_deep_requests"], 0)
        self.assertEqual(info["current_deep_coder_count"], 0)

    def test_deep_request_budgeting(self):
        """Test DEEP request budgeting logic."""
        # Initially all DEEP requests should be allowed
        for i in range(5):  # 5 per target per hour
            self.assertTrue(self.budget_tracker.can_request("deep", "target1"))
            self.budget_tracker.record_request("deep", "target1")
            self.budget_tracker.release_request("deep", "target1")

        # Next DEEP request should be denied
        self.assertFalse(self.budget_tracker.can_request("deep", "target1"))

        # Global budget should also be tracked
        self.budget_tracker.record_request("deep", "target2")
        self.budget_tracker.release_request("deep", "target2")
        self.budget_tracker.record_request("deep", "target3")
        self.budget_tracker.release_request("deep", "target3")
        self.budget_tracker.record_request("deep", "target4")
        self.budget_tracker.release_request("deep", "target4")
        self.budget_tracker.record_request("deep", "target5")
        self.budget_tracker.release_request("deep", "target5")
        self.budget_tracker.record_request("deep", "target6")
        self.budget_tracker.release_request("deep", "target6")

        # Global budget is 20, so we should be able to make more requests
        # but we're at 6 global requests now, so we should be able to make 14 more
        # But we're still within the per-target limit for target1

        # Test that we can still make requests to different targets
        self.assertTrue(self.budget_tracker.can_request("deep", "target7"))
        self.budget_tracker.record_request("deep", "target7")
        self.budget_tracker.release_request("deep", "target7")

        # Test that we can't make more requests to target1
        self.assertFalse(self.budget_tracker.can_request("deep", "target1"))

    def test_coder_request_budgeting(self):
        """Test CODER request budgeting logic."""
        # Initially all CODER requests should be allowed
        for i in range(3):  # 3 per target per hour
            self.assertTrue(self.budget_tracker.can_request("coder", "target1"))
            self.budget_tracker.record_request("coder", "target1")
            self.budget_tracker.release_request("coder", "target1")

        # Next CODER request should be denied
        self.assertFalse(self.budget_tracker.can_request("coder", "target1"))

    def test_concurrency_limiting(self):
        """Test that concurrency limits are enforced."""
        # Test that we can make up to MAX_DEEP_CODER_CONCURRENCY requests
        for i in range(3):  # MAX_DEEP_CODER_CONCURRENCY = 3
            self.assertTrue(self.budget_tracker.can_request("deep", f"target{i}"))
            self.budget_tracker.record_request("deep", f"target{i}")

        # Next request should be denied due to concurrency limit
        self.assertFalse(self.budget_tracker.can_request("deep", "target3"))

        # Release one request and it should be allowed again
        self.budget_tracker.release_request("deep", "target0")
        self.assertTrue(self.budget_tracker.can_request("deep", "target3"))

        # Test with coder requests
        self.assertTrue(self.budget_tracker.can_request("coder", "target4"))
        self.budget_tracker.record_request("coder", "target4")
        self.assertFalse(self.budget_tracker.can_request("coder", "target5"))

        # Next coder request should be denied due to concurrency limit
        self.assertFalse(self.budget_tracker.can_request("coder", "target6"))

    def test_budget_reset(self):
        """Test that budgets reset after an hour."""
        # Fill up the budget
        for i in range(5):
            self.assertTrue(self.budget_tracker.can_request("deep", "target1"))
            self.budget_tracker.record_request("deep", "target1")
            self.budget_tracker.release_request("deep", "target1")

        # Now we should be denied
        self.assertFalse(self.budget_tracker.can_request("deep", "target1"))

        # Simulate one hour passing relative to the target's reset timestamp.
        target_last_reset = self.budget_tracker._target_budgets["target1"].last_reset
        global_reset = self.budget_tracker._global_reset_time

        with patch("time.monotonic", return_value=max(target_last_reset, global_reset) + 3600):
            # Both global and per-target budgets should expire.
            self.assertTrue(self.budget_tracker.can_request("deep", "target1"))

    def test_multiple_targets(self):
        """Test that different targets have independent budgets."""
        # Fill up target1's budget
        for i in range(5):
            self.assertTrue(self.budget_tracker.can_request("deep", "target1"))
            self.budget_tracker.record_request("deep", "target1")
            self.budget_tracker.release_request("deep", "target1")

        # Should be denied for target1
        self.assertFalse(self.budget_tracker.can_request("deep", "target1"))

        # But should be allowed for target2
        self.assertTrue(self.budget_tracker.can_request("deep", "target2"))
        self.budget_tracker.record_request("deep", "target2")
        self.budget_tracker.release_request("deep", "target2")

        # Both targets should be able to make requests
        self.assertFalse(self.budget_tracker.can_request("deep", "target1"))
        self.assertTrue(self.budget_tracker.can_request("deep", "target2"))

    def test_duplicate_release_does_not_underflow_concurrency(self):
        self.budget_tracker.record_request("deep", "target1")
        self.budget_tracker.release_request("deep", "target1")
        self.budget_tracker.release_request("deep", "target1")

        info = self.budget_tracker.get_budget_info()
        self.assertEqual(info["current_deep_coder_count"], 0)
        self.assertNotIn("target1", info["active_targets"])

    def test_same_target_multiple_active_requests(self):
        self.budget_tracker.record_request("deep", "target1")
        self.budget_tracker.record_request("coder", "target1")

        self.budget_tracker.release_request("deep", "target1")
        info = self.budget_tracker.get_budget_info()
        self.assertEqual(info["current_deep_coder_count"], 1)
        self.assertIn("target1", info["active_targets"])

        self.budget_tracker.release_request("coder", "target1")
        info = self.budget_tracker.get_budget_info()
        self.assertEqual(info["current_deep_coder_count"], 0)
        self.assertNotIn("target1", info["active_targets"])

    def test_request_lifecycle(self):
        """Test that request lifecycle (can_request -> record_request -> release_request) works correctly."""
        # Can request should return True initially
        self.assertTrue(self.budget_tracker.can_request("deep", "target1"))

        # Record the request
        self.budget_tracker.record_request("deep", "target1")

        # Now we should be at 1 concurrent request
        info = self.budget_tracker.get_budget_info()
        self.assertEqual(info["current_deep_coder_count"], 1)
        self.assertIn("target1", info["active_targets"])

        # Release the request
        self.budget_tracker.release_request("deep", "target1")

        # Now we should be at 0 concurrent requests
        info = self.budget_tracker.get_budget_info()
        self.assertEqual(info["current_deep_coder_count"], 0)
        self.assertNotIn("target1", info["active_targets"])

    def test_mixed_request_types(self):
        """Test that different request types don't interfere with each other."""
        # Test that fast/plan/embed don't affect DEEP/CODER budgets
        for i in range(5):
            self.assertTrue(self.budget_tracker.can_request("deep", "target1"))
            self.budget_tracker.record_request("deep", "target1")
            self.budget_tracker.release_request("deep", "target1")

        # Should be denied now
        self.assertFalse(self.budget_tracker.can_request("deep", "target1"))

        # But fast requests should still be allowed
        self.assertTrue(self.budget_tracker.can_request("fast", "target1"))
        self.budget_tracker.record_request("fast", "target1")

        # And plan requests should be allowed
        self.assertTrue(self.budget_tracker.can_request("plan", "target1"))
        self.budget_tracker.record_request("plan", "target1")

        # And embed requests should be allowed
        self.assertTrue(self.budget_tracker.can_request("embed", "target1"))
        self.budget_tracker.record_request("embed", "target1")

        # DEEP should still be denied
        self.assertFalse(self.budget_tracker.can_request("deep", "target1"))


if __name__ == '__main__':
    unittest.main()