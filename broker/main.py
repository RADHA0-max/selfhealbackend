#!/usr/bin/env python3
"""
NanoClaw LLM Broker - File-based RPC system.

This broker handles file-based communication between the NanoClaw agent
and the LiteLLM inference gateway, enforcing all security and budget constraints.
"""

from __future__ import annotations

import asyncio
import shutil
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List

from broker.budget import BudgetTracker
from broker.config import load_config
from broker.litellm_client import LiteLLMClient
from broker.protocol import (
    MAX_REQUEST_BYTES,
    RPCRequest,
    parse_request,
    make_response,
    new_request_id,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class Broker:
    """Main broker class that handles file-based RPC communication."""

    def __init__(self, config_path: str = "/broker/config.py") -> None:
        self.config = load_config()
        self.budget_tracker = BudgetTracker()
        self._running = False
        self.litellm_client: LiteLLMClient | None = None

        # Ensure directories exist
        for dir_path in [
            self.config.rpc_in_dir,
            self.config.rpc_out_dir,
            self.config.rpc_failed_dir,
        ]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        """Start the broker loop."""
        logger.info("Starting broker...")
        self._running = True

        while self._running:
            try:
                await self._process_requests()
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
            except Exception as e:
                logger.error(f"Error in broker loop: {e}")
                await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the broker."""
        logger.info("Stopping broker...")
        self._running = False

    async def _process_requests(self) -> None:
        """Process all pending requests in the input directory."""
        in_dir = Path(self.config.rpc_in_dir)
        out_dir = Path(self.config.rpc_out_dir)
        failed_dir = Path(self.config.rpc_failed_dir)

        # Get all request files
        request_files = list(in_dir.glob("req-*.json"))

        # Process up to the queue limit
        for req_file in request_files[:self.config.max_queue_size]:
            try:
                # Read and parse the request
                if req_file.is_symlink():
                    raise ValueError("symlink requests prohibited")
                with req_file.open("rb") as request_handle:
                    raw_request = request_handle.read(MAX_REQUEST_BYTES + 1)
                if len(raw_request) > MAX_REQUEST_BYTES:
                    raise ValueError("request exceeds 64 KiB limit")

                request = parse_request(raw_request)

                # Both existing clients use either id.json or req-id.json naming.
                if req_file.stem not in (request.request_id, "req-" + request.request_id):
                    raise ValueError("request filename and ID differ")
                if (out_dir / f"resp-{request.request_id}.json").exists():
                    raise ValueError("response already exists; duplicate inference blocked")

                # Check if this request is allowed based on budgets
                if not self.budget_tracker.can_request(request.model, "default"):
                    logger.warning(
                        f"Budget exceeded for model {request.model}, deferring request"
                    )
                    (out_dir / f"resp-{request.request_id}.json").write_bytes(
                        make_response(request.request_id, error="model budget exhausted"))
                    # Move to failed directory for later processing
                    failed_file = failed_dir / req_file.name
                    shutil.move(str(req_file), str(failed_file))
                    continue

                # Record the request in budget tracker
                self.budget_tracker.record_request(request.model, "default")

                try:
                    # Initialize LiteLLM client if not already done
                    if self.litellm_client is None:
                        self.litellm_client = LiteLLMClient(self.config)

                    # Process the request by calling LiteLLM
                    response = await self._process_request_with_litellm(request)

                    # Publish the response atomically without overwriting an existing response.
                    response_file = out_dir / f"resp-{request.request_id}.json"
                    temp_file = out_dir / f".resp-{request.request_id}.tmp"
                    try:
                        with temp_file.open("xb") as handle:
                            handle.write(response)
                            handle.flush()
                        # Hard-link creation is atomic and fails if response_file exists.
                        temp_file.link_to(response_file)
                    finally:
                        try:
                            temp_file.unlink()
                        except FileNotFoundError:
                            pass

                    # Remove the processed request
                    req_file.unlink()
                finally:
                    # Always release the concurrency slot, even on failure.
                    self.budget_tracker.release_request(request.model, "default")

            except Exception as e:
                logger.error("Request rejected (%s)", type(e).__name__)
                # Move to failed directory
                failed_file = failed_dir / req_file.name
                shutil.move(str(req_file), str(failed_file))

    async def _process_request_with_litellm(self, request: RPCRequest) -> bytes:
        """Process a request by calling LiteLLM."""
        # Use the existing LiteLLM client to make the actual call
        logger.info(f"Processing request {request.request_id} for model {request.model}")

        # Call the LiteLLM client with the request
        async with self.litellm_client as client:
            response_bytes = await client.call_litellm(request)

        return response_bytes


async def main() -> None:
    """Main entry point."""
    broker = Broker()

    try:
        await broker.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        await broker.stop()


if __name__ == "__main__":
    asyncio.run(main())