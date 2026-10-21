"""
NanoClaw - Minimal Foundation for File-RPC Communication

This module provides the core foundation for NanoClaw to communicate
with the trusted broker through file-based RPC.
"""

__version__ = "0.1.0"
__author__ = "NanoClaw Team"

# Import the core components
from .config import NanoClawConfig
from .rpc_client import RPCClient
from .agent import NanoClawAgent

__all__ = ["NanoClawConfig", "RPCClient", "NanoClawAgent"]