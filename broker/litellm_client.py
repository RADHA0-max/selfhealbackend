"""
LiteLLM client for the NanoClaw broker.

This client handles communication with the LiteLLM inference gateway
and ensures all requests are properly formatted and validated.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Any, Dict, List, Optional

import aiohttp
from broker.config import BrokerConfig
from broker.protocol import RPCRequest, RPCResponse, make_response, unique_fields, MAX_RESPONSE_BYTES


logger = logging.getLogger(__name__)


class LiteLLMClient:
    """Client for communicating with LiteLLM inference gateway."""

    def __init__(self, config: BrokerConfig) -> None:
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> LiteLLMClient:
        """Enter the async context manager."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager."""
        if self.session:
            await self.session.close()

    async def call_litellm(self, request: RPCRequest) -> bytes:
        """
        Call LiteLLM with the given request and return the response.

        Args:
            request: The RPC request to send to LiteLLM

        Returns:
            The response bytes from LiteLLM
        """
        if not self.session:
            raise RuntimeError("LiteLLMClient not initialized")

        # Determine the endpoint based on model type
        if request.model == "embed":
            endpoint = f"{self.config.litellm_base_url}/v1/embeddings"
        else:
            endpoint = f"{self.config.litellm_base_url}/v1/chat/completions"

        # Prepare the request payload for LiteLLM
        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "input": request.input,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        headers = {
            "Authorization": f"Bearer {self.config.litellm_master_key}",
            "Content-Type": "application/json",
        }

        try:
            logger.info(f"Calling LiteLLM for model {request.model} at endpoint {endpoint}")

            async with self.session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise aiohttp.ClientError("backend unavailable")

                raw = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise ValueError("backend response too large")
                response_data = json.loads(raw, object_pairs_hook=unique_fields)
                if not isinstance(response_data, dict):
                    raise ValueError("invalid backend response")

                # Extract content from the response
                content = ""
                embedding = None
                if request.model == "embed":
                    # For embeddings, extract the embedding array
                    if "data" in response_data and response_data["data"]:
                        embedding = response_data["data"][0]["embedding"]
                else:
                    # For chat completions, extract content
                    if "choices" in response_data and response_data["choices"]:
                        choice = response_data["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            content = choice["message"]["content"]
                        elif "delta" in choice and "content" in choice["delta"]:
                            content = choice["delta"]["content"]

                if request.model == "embed":
                    if not isinstance(embedding, list) or not embedding or any(
                            type(x) not in (int, float) or not math.isfinite(x) for x in embedding):
                        raise ValueError("invalid embedding")
                elif not isinstance(content, str) or not content.strip():
                    raise ValueError("missing model content")
                logger.info("LiteLLM response received")

                return make_response(
                    request_id=request.request_id,
                    content=content,
                    embedding=embedding,
                )

        except Exception as e:
            logger.error("LiteLLM call failed (%s)", type(e).__name__)
            return make_response(
                request_id=request.request_id,
                error="inference timeout" if isinstance(e, asyncio.TimeoutError) else "inference backend failed",
            )