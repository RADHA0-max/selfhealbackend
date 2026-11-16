"""Offline tests for rate-limited diagnosis transport."""

import unittest

from experiments.rate_limited_transport_p06 import RateLimitedTransport


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeTransport:
    def __init__(self):
        self.calls = 0

    def call(self, *args, **kwargs):
        self.calls += 1
        return {"ok": True, "content": "{}"}


class RateLimitedTransportTests(unittest.TestCase):

    def test_enforces_minimum_spacing(self):
        clock = FakeClock()
        transport = FakeTransport()

        limited = RateLimitedTransport(
            transport,
            interval_seconds=2.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )

        limited.call("fast", [])
        self.assertEqual(clock.now, 0.0)

        limited.call("fast", [])
        self.assertEqual(clock.now, 2.0)

        limited.call("fast", [])
        self.assertEqual(clock.now, 4.0)
        self.assertEqual(transport.calls, 3)

    def test_rejects_request_101(self):
        transport = FakeTransport()
        clock = FakeClock()

        limited = RateLimitedTransport(
            transport,
            interval_seconds=1.0,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )

        for _ in range(100):
            limited.call("fast", [])

        with self.assertRaises(RuntimeError):
            limited.call("fast", [])

        self.assertEqual(transport.calls, 100)

    def test_rejects_invalid_intervals(self):
        for value in (0, -1, 61, True, "2"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    RateLimitedTransport(
                        FakeTransport(),
                        interval_seconds=value,
                    )


if __name__ == "__main__":
    unittest.main()
