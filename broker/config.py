from __future__ import annotations

import os
from dataclasses import dataclass


LITELLM_BASE_URL = os.environ.get(
    "LITELLM_BASE_URL",
    "http://litellm:4000",
)

# Validate that LITELLM_BASE_URL is exactly the trusted value
if LITELLM_BASE_URL != "http://litellm:4000":
    raise ValueError(
        f"Invalid LITELLM_BASE_URL: {LITELLM_BASE_URL}. "
        "Only 'http://litellm:4000' is allowed for security reasons."
    )

LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")

RPC_IN_DIR = os.environ.get(
    "RPC_IN_DIR",
    "/workspace/llm_rpc/in",
)

RPC_OUT_DIR = os.environ.get(
    "RPC_OUT_DIR",
    "/workspace/llm_rpc/out",
)

RPC_FAILED_DIR = os.environ.get(
    "RPC_FAILED_DIR",
    "/workspace/llm_rpc/failed",
)


MAX_QUEUE_SIZE = 8


# Per-target hourly budgets.
DEEP_PER_TARGET_PER_HOUR = 5
CODER_PER_TARGET_PER_HOUR = 3

# Global hourly budget.
DEEP_GLOBAL_PER_HOUR = 20

# Maximum number of simultaneous DEEP/CODER requests.
MAX_DEEP_CODER_CONCURRENCY = 3


# Only these model aliases may ever be sent to LiteLLM.
ALLOWED_MODELS = frozenset(
    {
        "fast",
        "plan",
        "deep",
        "coder",
        "embed",
    }
)


@dataclass(frozen=True)
class BrokerConfig:
    litellm_base_url: str
    litellm_master_key: str

    rpc_in_dir: str
    rpc_out_dir: str
    rpc_failed_dir: str

    max_queue_size: int

    deep_per_target_per_hour: int
    coder_per_target_per_hour: int
    deep_global_per_hour: int

    max_deep_coder_concurrency: int


def load_config() -> BrokerConfig:
    if not LITELLM_MASTER_KEY:
        raise RuntimeError(
            "LITELLM_MASTER_KEY environment variable is required"
        )

    return BrokerConfig(
        litellm_base_url=LITELLM_BASE_URL.rstrip("/"),
        litellm_master_key=LITELLM_MASTER_KEY,
        rpc_in_dir=RPC_IN_DIR,
        rpc_out_dir=RPC_OUT_DIR,
        rpc_failed_dir=RPC_FAILED_DIR,
        max_queue_size=MAX_QUEUE_SIZE,
        deep_per_target_per_hour=DEEP_PER_TARGET_PER_HOUR,
        coder_per_target_per_hour=CODER_PER_TARGET_PER_HOUR,
        deep_global_per_hour=DEEP_GLOBAL_PER_HOUR,
        max_deep_coder_concurrency=MAX_DEEP_CODER_CONCURRENCY,
    )