"""
NanoClaw Configuration

Configuration for NanoClaw's file-RPC communication with the trusted broker.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any


class NanoClawConfig:
    """Configuration class for NanoClaw RPC communication."""

    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize NanoClaw configuration.

        Args:
            base_dir: Base directory for RPC files. If None, uses default.
        """
        if base_dir is None:
            # Default to the llm_rpc directory in the workspace for production
            self.base_dir = Path("/workspace/llm_rpc")
        else:
            self.base_dir = Path(base_dir)

        # RPC directories
        self.in_dir = self.base_dir / "in"
        self.out_dir = self.base_dir / "out"
        self.failed_dir = self.base_dir / "failed"

        # Ensure directories exist
        self.in_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

        # Model routing aliases
        self.model_aliases = {
            "fast": "fast",
            "plan": "plan",
            "deep": "deep",
            "coder": "coder",
            "embed": "embed"
        }

        # Allowed model backends (logical aliases only)
        self.allowed_backends = set(self.model_aliases.values())

        # RPC timeout in seconds
        self.rpc_timeout = 30

        # Maximum request size in bytes
        self.max_request_size = 64 * 1024  # 64 KB

        # Queue limit
        self.queue_limit = 8

    def get_model_backend(self, alias: str) -> str:
        """
        Get the actual backend name for a model alias.

        Args:
            alias: Model alias (fast, plan, deep, coder, embed)

        Returns:
            Backend name

        Raises:
            ValueError: If alias is not recognized
        """
        if alias not in self.model_aliases:
            raise ValueError(f"Unknown model alias: {alias}")
        return self.model_aliases[alias]

    def validate_backend(self, backend: str) -> bool:
        """
        Validate that a backend is allowed.

        Args:
            backend: Backend name to validate

        Returns:
            True if allowed, False otherwise
        """
        return backend in self.allowed_backends

    def get_rpc_paths(self) -> Dict[str, Path]:
        """
        Get all RPC directory paths.

        Returns:
            Dictionary of RPC paths
        """
        return {
            "in": self.in_dir,
            "out": self.out_dir,
            "failed": self.failed_dir
        }