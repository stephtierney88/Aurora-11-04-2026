import io
import threading
import unittest

from smoke_watchdog import SmokeWatchdog


class SmokeWatchdogTests(unittest.TestCase):
    def test_invalid_intervals_rejected(self):
        for value in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                SmokeWatchdog(value)

    def test_repeated_diagnostics_run_off_caller_and_cleanup(self):
        called = threading.Event()
        threads = []
        def dump(**kwargs):
            self.assertTrue(kwargs['all_threads'])
            threads.append(threading.current_thread().name)
            if len(threads) >= 2: called.set()
        with SmokeWatchdog(.01, stream=io.StringIO(), dump=dump) as watchdog:
            self.assertTrue(called.wait(2))
        self.assertTrue(watchdog.snapshot()['thread_stopped'])
        self.assertGreaterEqual(watchdog.dumps, 2)
        self.assertEqual(set(threads), {'aurora-smoke-diagnostics'})

    def test_cancel_before_interval_and_idempotent_close(self):
        stream = io.StringIO()
        with SmokeWatchdog(60, stream=stream, dump=lambda **_: self.fail('Unexpected dump')) as watchdog:
            watchdog.close()
        self.assertEqual(watchdog.dumps, 0)
        self.assertEqual(stream.getvalue(), '')
        with self.assertRaises(RuntimeError): watchdog.__enter__()

    def test_failure_is_observable_and_stops_retrying(self):
        called = threading.Event()
        def fail(**_):
            called.set()
            raise OSError('fixture stream failure')
        with SmokeWatchdog(.01, stream=io.StringIO(), dump=fail) as watchdog:
            self.assertTrue(called.wait(2))
        self.assertEqual(watchdog.error, 'OSError')
        self.assertEqual(watchdog.dumps, 0)
        self.assertTrue(watchdog.snapshot()['thread_stopped'])

    def test_exception_in_body_still_stops_owned_thread(self):
        with self.assertRaisesRegex(RuntimeError, 'fixture body'):
            with SmokeWatchdog(60, stream=io.StringIO()) as watchdog:
                raise RuntimeError('fixture body')
        self.assertTrue(watchdog.snapshot()['thread_stopped'])


if __name__ == '__main__':
    unittest.main()
