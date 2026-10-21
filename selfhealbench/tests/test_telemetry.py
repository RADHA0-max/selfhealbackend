import copy
import unittest
from unittest.mock import patch

from selfhealbench.bench.demo import MockBackend
from selfhealbench.bench.live import IsolatedBackend
from selfhealbench.bench.pilot import verify
from selfhealbench.bench.run import load_scenarios
from selfhealbench.bench.scoring import summarize, verified_history
from selfhealbench.bench.telemetry import complete_evidence, prometheus_up, tempo_search, error_rate_verified
from selfhealbench.tests.test_runner import approved_config


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.collected = MockBackend().evidence()

    def test_valid_complete_fixture_and_down_metric(self):
        self.assertTrue(complete_evidence(self.collected))
        self.collected['evidence']['prometheus']['up']['data']['result'][0]['value'][1] = '0'
        self.assertTrue(complete_evidence(self.collected))  # complete is not healthy

    def test_malformed_stale_duplicate_and_unowned_metrics(self):
        valid = self.collected['evidence']['prometheus']['up']
        for change in (
            lambda v: v.update(status='error'),
            lambda v: v['data'].update(resultType='matrix'),
            lambda v: v['data']['result'].pop(),
            lambda v: v['data']['result'].__setitem__(0, v['data']['result'][1]),
            lambda v: v['data']['result'][0]['metric'].update(instance='other:8080'),
            lambda v: v['data']['result'][0]['metric'].update(job='other'),
            lambda v: v['data']['result'][0].update(value=[969, '1']),
            lambda v: v['data']['result'][0].update(value=[1001, '1']),
            lambda v: v['data']['result'][0].update(value=[float('nan'), '1']),
            lambda v: v['data']['result'][0].update(value=[1000, 'NaN']),
            lambda v: v['data']['result'][0].update(value=[1000, True]),
        ):
            value=copy.deepcopy(valid); change(value)
            with self.subTest(value=value), self.assertRaises(ValueError): prometheus_up(value,1000)

    def test_missing_stale_future_duplicate_or_unowned_traces(self):
        valid=self.collected['tempo_search']
        for change in (
            lambda v: v.update(traces=[]),
            lambda v: v['traces'][0].update(traceID='invalid'),
            lambda v: v['traces'][0].update(rootServiceName='unrelated'),
            lambda v: v['traces'][0].update(startTimeUnixNano='969000000000'),
            lambda v: v['traces'][0].update(startTimeUnixNano='1001000000000'),
            lambda v: v['traces'].append(v['traces'][0]),
        ):
            value=copy.deepcopy(valid);change(value)
            with self.assertRaises(ValueError): tempo_search(value,1000)

    def test_completeness_rejects_arbitrary_truthy_blobs_and_missing_fields(self):
        for change in (
            lambda v: v.update(evidence=[]),
            lambda v: v.update(collection_errors=['tempo']),
            lambda v: v.pop('collected_at'),
            lambda v: v.pop('tempo_search'),
            lambda v: v['evidence'].update(prometheus={'error':'unavailable'}),
            lambda v: v['evidence'].update(docker_logs=''),
            lambda v: v['evidence']['probes'].pop('db'),
            lambda v: v['evidence']['probes']['db'].update(latency_ms=float('nan')),
        ):
            value=copy.deepcopy(self.collected);change(value)
            self.assertFalse(complete_evidence(value))

    def test_histories_store_sanitized_observations_and_recompute_health(self):
        probes=MockBackend().probe()
        probes['db']['body']['password']='fixture-secret'
        probes['db']['authorization']='fixture-secret'
        ticks=[0]
        result=verify(lambda:probes,clock=lambda:ticks[0],sleep=lambda n:ticks.__setitem__(0,ticks[0]+n))
        self.assertTrue(verified_history(result))
        self.assertNotIn('fixture-secret',str(result))
        result['history'][-1]['probes']['db']['status']=503
        self.assertFalse(verified_history(result))  # even though ok is still true

    def test_history_flags_without_observations_or_sample_spacing_fail(self):
        result=MockBackend().verify()
        result['history'][1]['elapsed_seconds']=.1
        self.assertFalse(verified_history(result))
        result=MockBackend().verify()
        result['history'][1].pop('probes')
        self.assertFalse(verified_history(result))

    def test_late_probe_cannot_establish_recovery(self):
        ticks=[0]
        def slow():
            ticks[0]+=21
            return MockBackend().probe()
        result=verify(slow,clock=lambda:ticks[0],sleep=lambda _:None)
        self.assertFalse(result['recovered'])
        self.assertEqual(result['history'],[])

    def test_error_windows_require_actual_samples_and_zero_recovered_errors(self):
        value={'before': {'requests':100,'errors':20,'start':0,'end':10},
               'after': {'requests':100,'errors':0,'start':10,'end':20}}
        self.assertTrue(error_rate_verified(value))
        for change in (
            lambda v:v['after'].update(requests=0),
            lambda v:v['after'].update(errors=1),
            lambda v:v['after'].update(errors=-1),
            lambda v:v['after'].update(start=5),
            lambda v:v['after'].update(end=float('nan')),
        ):
            bad=copy.deepcopy(value);change(bad)
            self.assertFalse(error_rate_verified(bad))

    def test_malformed_records_score_failed_without_crashing(self):
        for record in ([], 'invalid', {'status':'ok','before':None}, {'status':'ok','before':{'evidence':[]}}):
            report=summarize(load_scenarios(), {'SHB-001':record},mode='live')
            self.assertEqual(report['recovery_success'],0)
            self.assertEqual(report['invalid_decisions'],1)

    def test_collection_validates_http_and_application_status_without_docker(self):
        backend=IsolatedBackend(approved_config(),'fixture-token-123456')
        with patch.object(backend,'assert_ready'), patch.object(backend,'_docker',return_value='fixture logs'), patch.object(backend,'probe',return_value=MockBackend().probe()), patch.object(backend,'_http') as http:
            backend.ids={s:s for s in ('api','db','worker','auth')}
            http.side_effect=[{'status':503,'body':self.collected['evidence']['prometheus']['up']},
                              {'status':200,'body':{'traces':[]}}]
            result=backend.evidence()
        self.assertEqual(result['collection_errors'],['prometheus:up','tempo:search'])
        self.assertFalse(complete_evidence(result))
