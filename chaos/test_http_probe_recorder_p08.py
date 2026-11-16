"""HTTP probe recorder safety tests without network access."""

import unittest

from chaos.http_probe_recorder import (
    ProbeError,
    record_http_probes,
    validate_probe_url,
)


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self):
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        return FakeResponse()


class ProbeRecorderTests(unittest.TestCase):

    def test_loopback_health_allowed(self):
        self.assertEqual(
            validate_probe_url("http://127.0.0.1:18080/health"),
            "http://127.0.0.1:18080/health",
        )

    def test_non_loopback_rejected(self):
        for url in (
            "http://8.8.8.8:80/health",
            "http://10.0.0.1:80/health",
            "http://example.com:80/health",
            "https://127.0.0.1:18080/health",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ProbeError):
                    validate_probe_url(url)

    def test_unsafe_paths_rejected(self):
        for url in (
            "http://127.0.0.1:18080/admin",
            "http://127.0.0.1:18080/health?token=x",
            "http://127.0.0.1:18080/ready#fragment",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ProbeError):
                    validate_probe_url(url)

    def test_fake_probe_collection(self):
        opener = FakeOpener()
        tick = [0.0]

        def clock():
            tick[0] += 0.1
            return tick[0]

        events = record_http_probes(
            "http://127.0.0.1:18080/health",
            count=3,
            interval_seconds=0.1,
            opener=opener,
            clock=clock,
            sleep=lambda seconds: None,
        )

        self.assertEqual(opener.calls, 3)
        self.assertEqual(len(events), 3)
        self.assertTrue(all(e["status"] == 200 for e in events))

    def test_probe_count_bounded(self):
        with self.assertRaises(ProbeError):
            record_http_probes(
                "http://127.0.0.1:18080/health",
                count=100,
            )

    def test_invalid_target_rejected(self):
        with self.assertRaises(ProbeError):
            record_http_probes(
                "http://127.0.0.1:18080/health",
                target="shell",
            )


if __name__ == "__main__":
    unittest.main()
