"""Pure telemetry validation; no I/O and no authority to recover a service."""
import math
import re

SERVICES = frozenset(('api', 'db', 'worker', 'auth'))


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def fresh(stamp, collected_at):
    return number(stamp) and number(collected_at) and 0 <= collected_at - stamp <= 30


def probe_snapshot(probes):
    """Persist only bounded measurement fields, never body text/errors/secrets."""
    if not isinstance(probes, dict) or set(probes) != SERVICES:
        return {}
    result = {}
    for service, item in probes.items():
        if not isinstance(item, dict):
            return {}
        code, latency, body = item.get('status'), item.get('latency_ms'), item.get('body')
        if type(code) is not int or not 0 <= code <= 599 or not number(latency) or latency < 0 or not isinstance(body, dict):
            return {}
        result[service] = {'status': code, 'latency_ms': latency, 'body': {}}
        if body.get('service') in SERVICES:
            result[service]['body']['service'] = body['service']
        if body.get('status') in ('ok', 'error'):
            result[service]['body']['status'] = body['status']
    return result


def prometheus_up(body, collected_at):
    if not isinstance(body, dict) or body.get('status') != 'success':
        raise ValueError('prometheus response unavailable')
    data = body.get('data')
    if not isinstance(data, dict) or data.get('resultType') != 'vector':
        raise ValueError('prometheus vector required')
    rows = data.get('result')
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError('complete service metrics required')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('metric'), dict):
            raise ValueError('invalid metric row')
        metric, value = row['metric'], row.get('value')
        instance = metric.get('instance')
        if metric.get('job') != 'selfheal-services' or metric.get('__name__') != 'up' or instance not in {s + ':8080' for s in SERVICES} or instance in seen:
            raise ValueError('metric identity mismatch')
        seen.add(instance)
        if not isinstance(value, list) or len(value) != 2 or not fresh(value[0], collected_at) or value[1] not in ('0', '1'):
            raise ValueError('stale or invalid metric sample')
    return True


def tempo_search(body, collected_at):
    if not isinstance(body, dict) or not isinstance(body.get('traces'), list) or not 1 <= len(body['traces']) <= 20:
        raise ValueError('nonempty bounded trace evidence required')
    seen = set()
    for row in body['traces']:
        if not isinstance(row, dict):
            raise ValueError('invalid trace')
        identity, stamp = row.get('traceID'), row.get('startTimeUnixNano')
        if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{32}', identity) or identity in seen:
            raise ValueError('invalid trace identity')
        seen.add(identity)
        if row.get('rootServiceName') not in {'selfheal-' + s for s in SERVICES}:
            raise ValueError('unowned trace')
        if not isinstance(stamp, str) or not re.fullmatch(r'[0-9]{1,20}', stamp) or not fresh(int(stamp) / 1e9, collected_at):
            raise ValueError('stale trace')
    return True


def complete_evidence(before):
    """Validate against recorded collection time for deterministic replay scoring."""
    try:
        if not isinstance(before, dict) or before.get('collection_errors') != []:
            return False
        evidence = before.get('evidence')
        if not isinstance(evidence, dict) or not probe_snapshot(evidence.get('probes')):
            return False
        stamp = before.get('collected_at')
        if not number(stamp) or stamp < 0:
            return False
        logs = evidence.get('docker_logs')
        if not isinstance(logs, str) or not logs.strip() or len(logs.encode()) > 32000:
            return False
        prometheus_up(evidence['prometheus']['up'], stamp)
        tempo_search(before['tempo_search'], stamp)
        return True
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def error_rate_verified(value):
    """Optional measured windows: when supplied they must prove improvement.

    No requests, counter resets or missing time ranges cannot establish a rate.
    Raw counters are not inferred from the up metric.
    """
    if not isinstance(value, dict) or set(value) != {'before', 'after'}:
        return False
    rates = []
    windows = []
    for key in ('before', 'after'):
        row = value[key]
        if not isinstance(row, dict) or set(row) != {'requests', 'errors', 'start', 'end'}:
            return False
        total, errors = row['requests'], row['errors']
        if type(total) is not int or type(errors) is not int or total <= 0 or not 0 <= errors <= total:
            return False
        if not number(row['start']) or not number(row['end']) or not 0 <= row['start'] < row['end']:
            return False
        rates.append(errors / total)
        windows.append(row)
    return windows[1]['start'] >= windows[0]['end'] and rates[1] == 0 and rates[1] <= rates[0]
