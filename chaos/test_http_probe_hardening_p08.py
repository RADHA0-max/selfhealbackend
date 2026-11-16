"""Additional HTTP probe safety and precision tests; no network."""

import unittest
from urllib.error import HTTPError, URLError

from chaos.http_probe_recorder import (
    ProbeError,
    record_http_probes,
)


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ProbeHardeningTests(unittest.TestCase):

    def test_redirect_rejected(self):
        opener = FakeOpener(
            HTTPError(
                "http://127.0.0.1:18080/health",
                302,
                "Found",
                {},
                None,
            )
        )

        with self.assertRaises(ProbeError):
            record_http_probes(
                "http://127.0.0.1:18080/health",
                count=2,
                opener=opener,
            )

        self.assertEqual(opener.calls, 1)

    def test_connection_failure_rejected(self):
        opener = FakeOpener(URLError("connection refused"))

        with self.assertRaises(ProbeError):
            record_http_probes(
                "http://127.0.0.1:18080/health",
                count=2,
                opener=opener,
            )

        self.assertEqual(opener.calls, 1)

    def test_close_timestamps_remain_increasing(self):
        opener = FakeOpener(FakeResponse(200))
        ticks = iter([
            0.0,
            0.0001, 0.0002,
            0.0003, 0.0004,
            0.0005, 0.0006,
        ])

        events = record_http_probes(
            "http://127.0.0.1:18080/health",
            count=3,
            interval_seconds=0.1,
            clock=lambda: next(ticks),
            sleep=lambda _: None,
            opener=opener,
        )

        self.assertEqual(len(events), 3)
        self.assertLess(events[0]["time_ms"], events[1]["time_ms"])
        self.assertLess(events[1]["time_ms"], events[2]["time_ms"])

    def test_nonfinite_intervals_rejected(self):
        for interval in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(interval=interval):
                with self.assertRaises(ProbeError):
                    record_http_probes(
                        "http://127.0.0.1:18080/health",
                        interval_seconds=interval,
                    )


if __name__ == "__main__":
    unittest.main()
