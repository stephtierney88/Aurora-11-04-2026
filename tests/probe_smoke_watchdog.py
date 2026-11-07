"""Bounded, isolated diagnostic probe; no Tk, runtime, input, capture or network.

Default: exercise the cooperative watchdog. --compare-native-timer also tries
the old native timer in a disposable child; that child can crash on affected
interpreters. Logs/ownership stay in a new ignored output directory.
"""
from __future__ import annotations

import argparse
import ctypes
import faulthandler
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from smoke_watchdog import SmokeWatchdog


def probe_worker(mode, log, duration):
    if os.name == 'nt':
        ctypes.windll.kernel32.SetErrorMode(0x0002)  # No OS crash dialog from our child.
    stop = threading.Event()
    target = Path(__file__)
    def stat_loop():
        while not stop.wait(.001):
            target.stat()
            target.exists()
    threads = [threading.Thread(target=stat_loop, name=f'probe-stat-{index}') for index in range(3)]
    for thread in threads:
        thread.start()
    watchdog = None
    with log.open('w', encoding='utf-8') as stream:
        try:
            if mode == 'native_timer':
                faulthandler.dump_traceback_later(.01, repeat=True, file=stream)
            else:
                watchdog = SmokeWatchdog(.01, stream=stream).__enter__()
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                target.stat()
                time.sleep(.01)
        finally:
            if watchdog is not None:
                watchdog.close()
            else:
                faulthandler.cancel_dump_traceback_later()
            stop.set()
            for thread in threads:
                thread.join(2)
    proof = dict(mode=mode, threads_stopped=all(not thread.is_alive() for thread in threads),
                 diagnostics=watchdog.snapshot() if watchdog else None)
    print(json.dumps(proof), flush=True)


def run_probe(duration, compare_native=False):
    import psutil
    root = Path(__file__).resolve().parents[1]
    work = root/'output'/f'smoke-watchdog-probe-{time.time_ns()}'
    work.mkdir(parents=True)
    assert work.resolve().parent == (root/'output').resolve()
    rows = []
    modes = ('native_timer', 'cooperative') if compare_native else ('cooperative',)
    for mode in modes:
        log = work/f'{mode}.log'
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', mode,
            '--log', str(log), '--seconds', str(duration)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        owner = dict(pid=process.pid, created=psutil.Process(process.pid).create_time(), mode=mode)
        (work/f'{mode}-owner.json').write_text(json.dumps(owner), encoding='utf-8')
        timed_out = False
        try:
            out, err = process.communicate(timeout=duration+5)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            out, err = process.communicate(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        rows.append(dict(mode=mode, exit_code=process.returncode, timed_out=timed_out,
                         native_dump_count=log.read_text(errors='replace').count('Timeout') if log.exists() else 0,
                         proof=json.loads(out) if process.returncode == 0 else None,
                         stderr_present=bool(err), process_stopped=process.poll() is not None))
    result = dict(python=sys.version, seconds_per_child=duration, results=rows,
                  scope='Isolated diagnostic probe, not Aurora GUI or execution behavior.')
    (work/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(workspace=str(work), **result)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare-native-timer', action='store_true')
    parser.add_argument('--seconds', type=float, default=2)
    parser.add_argument('--worker', choices=('native_timer', 'cooperative'), help=argparse.SUPPRESS)
    parser.add_argument('--log', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not .2 <= args.seconds <= 10:
        parser.error('--seconds must be between 0.2 and 10')
    if args.worker:
        if not args.log:
            parser.error('--worker requires --log')
        probe_worker(args.worker, args.log, args.seconds)
    else:
        run_probe(args.seconds, args.compare_native_timer)
