"""Sequential, start-spaced RPC transport for bounded experiments."""

import time


class RateLimitedTransport:
    """Enforce a minimum interval between RPC request starts."""

    def __init__(self, transport, *, interval_seconds=2.0,
                 clock=time.monotonic, sleep=time.sleep):
        if not isinstance(interval_seconds, (int, float)):
            raise ValueError("invalid interval")
        if isinstance(interval_seconds, bool) or not 0 < interval_seconds <= 60:
            raise ValueError("interval must be within (0, 60] seconds")

        self.transport = transport
        self.interval = interval_seconds
        self.clock = clock
        self.sleep = sleep
        self.last_start = None
        self.calls = 0

    def call(self, model, messages, **kwargs):
        if self.calls >= 100:
            raise RuntimeError("100-request limit exceeded")

        if self.last_start is not None:
            remaining = self.interval - (self.clock() - self.last_start)
            if remaining > 0:
                self.sleep(remaining)

        self.last_start = self.clock()
        self.calls += 1

        # No retry: exactly one underlying call per invocation.
        return self.transport.call(model, messages, **kwargs)
