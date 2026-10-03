"""Bounded real-browser measurements after the complete acceptance drill.

Closed-loop latency includes body consumption and every production auth boundary.
This is a local synthetic workload, not a maximum-capacity or physical WAN claim.
"""
from __future__ import annotations

import json
import math
import threading
import urllib.request

from p1_lifecycle import run


def summarize(measurements: list[dict], elapsed_ms: float) -> dict:
    if not measurements or not math.isfinite(elapsed_ms) or elapsed_ms <= 0:
        raise ValueError('Nonempty measurements and positive elapsed time required')
    latencies = sorted(float(m['milliseconds']) for m in measurements)
    if any(not math.isfinite(v) or v < 0 for v in latencies):
        raise ValueError('Invalid browser latency')
    statuses: dict[str, int] = {}
    for measurement in measurements:
        key = str(measurement['status'])
        statuses[key] = statuses.get(key, 0) + 1
    return {
        'requests': len(measurements), 'errors': sum(v for k, v in statuses.items() if k != '200'),
        'statuses': statuses, 'elapsed_seconds': round(elapsed_ms / 1000, 3),
        'requests_per_second': round(len(measurements) * 1000 / elapsed_ms, 2),
        'latency_ms': {f'p{p}': round(latencies[math.ceil(p * len(latencies) / 100) - 1], 2)
                       for p in (50, 95, 99)},
    }


def measure(suffix: str, workloads: dict[str, dict]) -> dict:
    containers = run('docker', 'ps', '-q', '--filter', 'label=codex.p1.run=' + suffix).splitlines()
    inventory = json.loads(run('docker', 'inspect', *containers))
    names = {record['Name'].lstrip('/'): record['Name'].lstrip('/').replace(suffix, 'run') for record in inventory}
    images = {names[record['Name'].lstrip('/')]: record['Image'] for record in inventory}
    baseline: list[dict] = []
    loaded: list[dict] = []
    failures: list[str] = []
    stop = threading.Event()

    def sample(target: list[dict]) -> None:
        output = run('docker', 'stats', '--no-stream', '--format', '{{json .}}', *containers)
        for line in output.splitlines():
            record = json.loads(line)
            target.append({'service': names[record['Name']], 'cpu_percent': float(record['CPUPerc'].rstrip('%')),
                           'memory': record['MemUsage'], 'memory_percent': float(record['MemPerc'].rstrip('%'))})

    def collect() -> None:
        try:
            while not stop.is_set():
                sample(loaded)
                stop.wait(1)
        except Exception as error:
            failures.append(type(error).__name__)

    def batch(workload: dict, samples: int, concurrency: int) -> dict:
        command = {'actor': 'owner', 'headers': {}, **workload,
                   'benchmark': {'samples': samples, 'concurrency': concurrency}}
        request = urllib.request.Request('http://p1-browser:8765', data=json.dumps(command).encode(),
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.load(response)

    for _ in range(3):
        sample(baseline)
    # Warm the same real session/paths; warmup errors are never discarded.
    for name, workload in workloads.items():
        warm = batch(workload, 10, 1)
        summary = summarize(warm['measurements'], warm['elapsed_ms'])
        if summary['errors']:
            raise RuntimeError('Benchmark warmup failed: ' + name + ' ' + json.dumps(summary)
                               + ' session_cookie_before=' + str(warm['session_cookie_before'])
                               + ' session_cookie_after=' + str(warm['session_cookie_present']))
    results = []
    collector = threading.Thread(target=collect, daemon=True)
    collector.start()
    try:
        for concurrency in (1, 4, 8):
            for name, workload in workloads.items():
                rounds = []
                all_measurements = []
                elapsed_ms = 0.0
                for _ in range(3):
                    measured = batch(workload, 80, concurrency)
                    assert len(measured['measurements']) == 80, 'Incomplete browser batch'
                    rounds.append(summarize(measured['measurements'], measured['elapsed_ms']))
                    all_measurements.extend(measured['measurements'])
                    elapsed_ms += measured['elapsed_ms']
                summary = summarize(all_measurements, elapsed_ms)
                results.append({'workload': name, 'concurrency': concurrency, **summary, 'rounds': rounds})
                print('BENCH', name, 'concurrency=' + str(concurrency), json.dumps(summary), flush=True)
    finally:
        stop.set()
        collector.join(timeout=40)
    if collector.is_alive() or failures:
        raise RuntimeError('Container resource measurement failed: ' + ','.join(failures))
    if not loaded:
        raise RuntimeError('No loaded container resource samples')
    engine = json.loads(run('docker', 'info', '--format',
                            '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}},"version":"{{.ServerVersion}}"}'))
    return {'method': 'Chromium same-origin closed-loop; body consumed; nearest-rank percentiles',
            'warmup_requests_per_workload': 10, 'rounds': 3, 'samples_per_round': 80,
            'engine': engine, 'images': images, 'results': results,
            'resources': {'baseline': baseline, 'load': loaded},
            'errors': sum(result['errors'] for result in results)}
