import unittest
from unittest.mock import patch
from selfhealbench.bench.demo import demonstrate


class DemoTests(unittest.TestCase):
    def test_demo_is_synthetic_and_never_contacts_infrastructure(self):
        with patch('subprocess.run', side_effect=AssertionError('no subprocess')), patch(
                'urllib.request.build_opener', side_effect=AssertionError('no network')):
            report = demonstrate()
        self.assertEqual(report['mode'], 'mock_demonstration')
        self.assertEqual(report['completed'], 10)
        self.assertIsNone(report['live_recovery_success'])
        self.assertEqual(report['simulated_recovery_success'], 1)
        self.assertEqual(len(report['pending_live_scenarios']), 10)
        self.assertEqual(report['unnecessary_intervention']['count'], 0)
        self.assertTrue(report['audit'])
