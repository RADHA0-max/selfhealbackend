from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from broker.config import (
    DEEP_PER_TARGET_PER_HOUR,
    CODER_PER_TARGET_PER_HOUR,
    DEEP_GLOBAL_PER_HOUR,
    MAX_DEEP_CODER_CONCURRENCY,
    ALLOWED_MODELS,
)


@dataclass(frozen=True)
class BudgetState:
    """Represents the current budget state for a specific target."""
    deep_requests: int
    coder_requests: int
    last_reset: float


class BudgetTracker:
    """Tracks request budgets for DEEP and CODER models with time-based accounting."""

    def __init__(self) -> None:
        # Track per-target budgets (target -> BudgetState)
        self._target_budgets: Dict[str, BudgetState] = {}

        # Track global DEEP requests
        self._global_deep_requests: int = 0

        # Track current concurrent DEEP/CODER requests
        self._current_deep_coder_count: int = 0

        # Track the last reset time for global budget
        self._global_reset_time: float = time.monotonic()

        # Track which targets are currently using DEEP/CODER (for concurrency tracking)
        self._active_targets: Dict[str, int] = {}
        self._active_requests: Dict[Tuple[str, str], int] = {}

    def _reset_global_budget(self) -> None:
        """Reset global budget if an hour has passed."""
        now = time.monotonic()
        if now - self._global_reset_time >= 3600:  # 1 hour
            self._global_deep_requests = 0
            self._global_reset_time = now

    def _reset_target_budget(self, target: str) -> None:
        """Reset target budget if an hour has passed."""
        if target not in self._target_budgets:
            return

        now = time.monotonic()
        if now - self._target_budgets[target].last_reset >= 3600:  # 1 hour
            self._target_budgets[target] = BudgetState(
                deep_requests=0,
                coder_requests=0,
                last_reset=now
            )

    def _get_target_budget(self, target: str) -> BudgetState:
        """Get or initialize the budget state for a target."""
        if target not in self._target_budgets:
            self._target_budgets[target] = BudgetState(
                deep_requests=0,
                coder_requests=0,
                last_reset=time.monotonic()
            )
        else:
            self._reset_target_budget(target)

        return self._target_budgets[target]

    def can_request(self, model: str, target: str) -> bool:
        """
        Check if a request can be made for the given model and target.

        Returns True if the request is allowed, False otherwise.
        """
        # Fast/plan/embed are not subject to DEEP/CODER budgets
        if model in {"fast", "plan", "embed"}:
            return True

        # For DEEP/CODER models, check all applicable budgets
        if model == "deep":
            # Check global DEEP budget
            self._reset_global_budget()
            if self._global_deep_requests >= DEEP_GLOBAL_PER_HOUR:
                return False

            # Check per-target DEEP budget
            target_budget = self._get_target_budget(target)
            if target_budget.deep_requests >= DEEP_PER_TARGET_PER_HOUR:
                return False

        elif model == "coder":
            # Check per-target CODER budget
            target_budget = self._get_target_budget(target)
            if target_budget.coder_requests >= CODER_PER_TARGET_PER_HOUR:
                return False

        # Check concurrency limit for DEEP/CODER requests
        if model in {"deep", "coder"}:
            if self._current_deep_coder_count >= MAX_DEEP_CODER_CONCURRENCY:
                return False

        return True

    def record_request(self, model: str, target: str) -> None:
        """
        Record a request for the given model and target.
        This should be called after can_request() returns True.
        """
        # Fast/plan/embed are not subject to DEEP/CODER budgets
        if model in {"fast", "plan", "embed"}:
            return

        # For DEEP/CODER models, update budgets
        if model == "deep":
            # Update global DEEP count
            self._reset_global_budget()
            self._global_deep_requests += 1

            # Update per-target DEEP count
            target_budget = self._get_target_budget(target)
            self._target_budgets[target] = BudgetState(
                deep_requests=target_budget.deep_requests + 1,
                coder_requests=target_budget.coder_requests,
                last_reset=target_budget.last_reset
            )

        elif model == "coder":
            # Update per-target CODER count
            target_budget = self._get_target_budget(target)
            self._target_budgets[target] = BudgetState(
                deep_requests=target_budget.deep_requests,
                coder_requests=target_budget.coder_requests + 1,
                last_reset=target_budget.last_reset
            )

        # Update concurrency count for DEEP/CODER requests
        if model in {"deep", "coder"}:
            self._current_deep_coder_count += 1
            key = (model, target)
            self._active_requests[key] = self._active_requests.get(key, 0) + 1
            self._active_targets[target] = self._active_targets.get(target, 0) + 1

    def release_request(self, model: str, target: str) -> None:
        """
        Release a request for the given model and target.
        This should be called when a request completes.
        """
        # Fast/plan/embed are not subject to DEEP/CODER budgets
        if model in {"fast", "plan", "embed"}:
            return

        # Release only a matching active request; duplicate releases are harmless.
        if model not in {"deep", "coder"}:
            return

        key = (model, target)
        active_count = self._active_requests.get(key, 0)
        if active_count <= 0:
            return

        if active_count == 1:
            del self._active_requests[key]
        else:
            self._active_requests[key] = active_count - 1

        self._current_deep_coder_count = max(
            0, self._current_deep_coder_count - 1
        )

        target_count = self._active_targets.get(target, 0)
        if target_count <= 1:
            self._active_targets.pop(target, None)
        else:
            self._active_targets[target] = target_count - 1

    def get_budget_info(self) -> Dict[str, object]:
        """
        Get current budget information for debugging/testing.
        """
        return {
            "global_deep_requests": self._global_deep_requests,
            "current_deep_coder_count": self._current_deep_coder_count,
            "target_budgets": {
                target: {
                    "deep_requests": budget.deep_requests,
                    "coder_requests": budget.coder_requests,
                    "last_reset": budget.last_reset,
                }
                for target, budget in self._target_budgets.items()
            },
            "active_targets": list(self._active_targets.keys()),
        }