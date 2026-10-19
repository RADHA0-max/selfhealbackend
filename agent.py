"""
NanoClaw Agent

Minimal agent abstraction for NanoClaw that uses the RPC client
to communicate with the trusted broker.
"""

from typing import Dict, Any, List
from .rpc_client import RPCClient
from .config import NanoClawConfig


class NanoClawAgent:
    """Minimal agent abstraction for NanoClaw."""

    def __init__(self, config: None = None):
        """
        Initialize the NanoClaw agent.

        Args:
            config: NanoClaw configuration instance
        """
        self.config = config or NanoClawConfig()
        self.rpc_client = RPCClient(self.config)

    def _prepare_messages(self, system_prompt: str, user_prompt: str) -> List[Dict[str, str]]:
        """
        Prepare messages for the model.

        Args:
            system_prompt: System prompt for the model
            user_prompt: User prompt for the model

        Returns:
            List of message dictionaries
        """
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

    def make_request(self, model: str, system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Make a request to the broker using the RPC client.

        Args:
            model: Model alias (fast, plan, deep, coder, embed)
            system_prompt: System prompt for the model
            user_prompt: User prompt for the model
            **kwargs: Additional request parameters

        Returns:
            Response from the broker
        """
        messages = self._prepare_messages(system_prompt, user_prompt)
        return self.rpc_client.make_request(model, messages, **kwargs)

    def make_request_sync(self, model: str, system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Synchronous version of make_request.

        Args:
            model: Model alias (fast, plan, deep, coder, embed)
            system_prompt: System prompt for the model
            user_prompt: User prompt for the model
            **kwargs: Additional request parameters

        Returns:
            Response from the broker
        """
        return self.make_request(model, system_prompt, user_prompt, **kwargs)

    def triage(self, system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Make a request using the fast model for triage.

        Args:
            system_prompt: System prompt for the model
            user_prompt: User prompt for the model
            **kwargs: Additional request parameters

        Returns:
            Response from the broker
        """
        return self.make_request("fast", system_prompt, user_prompt, **kwargs)

    def plan(self, system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Make a request using the plan model.

        Args:
            system_prompt: System prompt for the model
            user_prompt: User prompt for the model
            **kwargs: Additional request parameters

        Returns:
            Response from the broker
        """
        return self.make_request("plan", system_prompt, user_prompt, **kwargs)

    def diagnose(self, system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Make a request using the deep model for diagnosis.

        Args:
            system_prompt: System prompt for the model
            user_prompt: User prompt for the model
            **kwargs: Additional request parameters

        Returns:
            Response from the broker
        """
        return self.make_request("deep", system_prompt, user_prompt, **kwargs)

    def patch(self, system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Make a request using the coder model for patch generation.

        Args:
            system_prompt: System prompt for the model
            user_prompt: User prompt for the model
            **kwargs: Additional request parameters

        Returns:
            Response from the broker
        """
        return self.make_request("coder", system_prompt, user_prompt, **kwargs)

    def recall(self, system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Make a request using the embed model for recall.

        Args:
            system_prompt: System prompt for the model
            user_prompt: User prompt for the model
            **kwargs: Additional request parameters

        Returns:
            Response from the broker
        """
        return self.make_request("embed", system_prompt, user_prompt, **kwargs)