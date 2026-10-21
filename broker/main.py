#!/usr/bin/env python3
"""
NanoClaw LLM Broker - File-based RPC system.

This broker handles file-based communication between the NanoClaw agent
and the LiteLLM inference gateway, enforcing all security and budget constraints.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
import itertools
from pathlib import Path

from broker.durability import Journal, publish, read_request, sync_directory
from broker.budget import BudgetTracker
from broker.config import load_config
from broker.litellm_client import LiteLLMClient
from broker.protocol import (
    RPCRequest,
    parse_request,
    make_response,
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
        # Only one process may own a queue batch. A crash leaves durable claims;
        # acquiring this lock later does not authorize repeating inference.
        state = getattr(self.config, "rpc_state_dir", None) or str(
            Path(self.config.rpc_failed_dir) / ".broker-state")
        try:
            with Journal(state) as journal:
                await self._process_owned_requests(journal)
        except BlockingIOError:
            return  # another broker owns this batch

    async def _process_owned_requests(self, journal) -> None:
        in_dir = Path(self.config.rpc_in_dir)
        out_dir = Path(self.config.rpc_out_dir)
        failed_dir = Path(self.config.rpc_failed_dir)
        # Memory bounded by the batch limit, unlike list(glob(...)). Producer-side
        # disk admission/quotas still require a separate deployment contract.
        request_files = list(itertools.islice(in_dir.glob("req-*.json"), self.config.max_queue_size))
        for req_file in request_files:
            claimed_file = journal.directory / ("pending-" + uuid.uuid4().hex)
            identity = None
            reserved = False
            request = None
            try:
                # Take the directory entry out of the producer namespace first.
                # Open the moved inode with O_NOFOLLOW/O_NONBLOCK, then fstat.
                req_file.rename(claimed_file)
                sync_directory(in_dir)
                sync_directory(journal.directory)
                raw = read_request(claimed_file)
                request = parse_request(raw)
                identity = request.request_id
                if req_file.stem not in (identity, "req-" + identity):
                    raise ValueError("request filename and ID differ")
                outcome, cached = journal.claim(identity, raw)
                response_file = out_dir / f"resp-{identity}.json"
                if outcome == "CONFLICT":
                    raise ValueError("request ID reused with different payload")
                if os.path.lexists(response_file):
                    journal.uncertain(identity)
                    raise ValueError("response already exists")
                if outcome == "COMPLETE":
                    publish(response_file, cached)
                elif outcome in ("CLAIMED", "UNCERTAIN"):
                    publish(response_file, make_response(identity, error="request outcome uncertain; reconciliation required"))
                    raise ValueError("uncertain request cannot be retried")
                else:
                    if not self.budget_tracker.can_request(request.model, "default"):
                        response = make_response(identity, error="model budget exhausted")
                        journal.finish(identity, response)
                        publish(response_file, response)
                        raise ValueError("model budget exhausted")
                    self.budget_tracker.record_request(request.model, "default")
                    reserved = True
                    if self.litellm_client is None:
                        self.litellm_client = LiteLLMClient(self.config)
                    response = await self._process_request_with_litellm(request)
                    # Persist response before publication. Publication failures may
                    # republish the cached response, never repeat the model call.
                    journal.finish(identity, response)
                    publish(response_file, response)
                claimed_file.unlink()
                sync_directory(journal.directory)
            except Exception as exc:
                if identity is not None:
                    journal.uncertain(identity)
                logger.error("Request rejected (%s)", type(exc).__name__)
                if os.path.lexists(claimed_file):
                    destination = failed_dir / req_file.name
                    if os.path.lexists(destination):
                        destination = failed_dir / (req_file.name + "." + uuid.uuid4().hex)
                    claimed_file.rename(destination)
                    sync_directory(failed_dir)
                    sync_directory(journal.directory)
            finally:
                if reserved:
                    self.budget_tracker.release_request(request.model, "default")

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