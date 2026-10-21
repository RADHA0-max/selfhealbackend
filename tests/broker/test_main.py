import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from broker.main import Broker


def test_litellm_failure_releases_concurrency_slot(tmp_path):
    rpc_in = tmp_path / "in"
    rpc_out = tmp_path / "out"
    rpc_failed = tmp_path / "failed"

    for directory in (rpc_in, rpc_out, rpc_failed):
        directory.mkdir()

    config = SimpleNamespace(
        rpc_in_dir=str(rpc_in),
        rpc_out_dir=str(rpc_out),
        rpc_failed_dir=str(rpc_failed),
        max_queue_size=8,
    )

    request_id = "budget-release-test"
    request_file = rpc_in / ("req-" + request_id + ".json")
    request_file.write_text(json.dumps({
        "request_id": request_id,
        "model": "deep",
        "messages": [{"role": "user", "content": "test"}],
        "max_tokens": 16,
    }))

    with patch("broker.main.load_config", return_value=config):
        broker = Broker()

    broker._process_request_with_litellm = AsyncMock(
        side_effect=RuntimeError("simulated LiteLLM failure")
    )

    asyncio.run(broker._process_requests())

    info = broker.budget_tracker.get_budget_info()
    assert info["current_deep_coder_count"] == 0
    assert "default" not in info["active_targets"]
    assert not request_file.exists()
    assert (rpc_failed / request_file.name).exists()
    assert info["global_deep_requests"] == 1


def test_existing_response_is_not_overwritten(tmp_path):
    rpc_in = tmp_path / "in"
    rpc_out = tmp_path / "out"
    rpc_failed = tmp_path / "failed"

    for directory in (rpc_in, rpc_out, rpc_failed):
        directory.mkdir()

    config = SimpleNamespace(
        rpc_in_dir=str(rpc_in),
        rpc_out_dir=str(rpc_out),
        rpc_failed_dir=str(rpc_failed),
        max_queue_size=8,
    )

    request_id = "response-collision-test"
    request_file = rpc_in / ("req-" + request_id + ".json")
    request_file.write_text(json.dumps({
        "request_id": request_id,
        "model": "deep",
        "messages": [{"role": "user", "content": "test"}],
        "max_tokens": 16,
    }))

    response_file = rpc_out / ("resp-" + request_id + ".json")
    original_response = b'{"original": true}'
    response_file.write_bytes(original_response)

    with patch("broker.main.load_config", return_value=config):
        broker = Broker()

    broker._process_request_with_litellm = AsyncMock(
        return_value=b'{"replacement": true}'
    )

    asyncio.run(broker._process_requests())

    assert response_file.read_bytes() == original_response
    assert not (rpc_out / (".resp-" + request_id + ".tmp")).exists()
    assert not request_file.exists()
    assert (rpc_failed / request_file.name).exists()

