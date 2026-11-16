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

    def test_close_timestamps_rejected(self):
        from chaos.http_probe_recorder import ProbeError

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        class Opener:
            def open(self, request, timeout):
                return Response()

        times = iter([0.0, 0.0, 0.0, 0.0001, 0.0002])

        with self.assertRaises(ProbeError):
            record_http_probes(
                "http://127.0.0.1:18080/ready",
                count=2,
                interval_seconds=0.1,
                opener=Opener(),
                clock=lambda: next(times),
                sleep=lambda _: None,
            )

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
