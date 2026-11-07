"""Bounded screen-change observation through the existing capture service.

No input, image acquisition, file I/O or model call lives here. A changed sampled
fingerprint is evidence of pixel change, never semantic completion/stability.
"""
import copy
import math
import re
import time

from aurora_runtime_work import WorkCancelled

COMMAND = 'OBSERVE_SCREEN_CHANGE'
RESULT_SCHEMA = 'aurora_observation_result_v1'
MAX_SAMPLES = 12


def parse_observation_arguments(args):
    if not 1 <= len(args) <= 3 or not re.fullmatch(r'[a-fA-F0-9]{32}', str(args[0])):
        raise ValueError('OBSERVE_SCREEN_CHANGE(frame_id[, timeout_seconds, poll_seconds]) requires an exact 32-character frame ID.')
    values = []
    for value, low, high, label in ((args[1] if len(args) > 1 else 3, .25, 8, 'timeout'),
                                   (args[2] if len(args) > 2 else .25, .1, 2, 'poll interval')):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f'Observation {label} must be numeric.') from None
        if isinstance(value, bool) or not math.isfinite(number) or not low <= number <= high:
            raise ValueError(f'Observation {label} must be between {low} and {high} seconds.')
        values.append(number)
    if values[1] > values[0]:
        raise ValueError('Observation poll interval cannot exceed the timeout.')
    return str(args[0]), *values


def describe_observation_contract():
    return dict(parameter_validation='pre_dispatch', min_arguments=1, max_arguments=3,
        parameters=[dict(name='frame_id', type='string', required=True, pattern='[a-fA-F0-9]{32}'),
                    dict(name='timeout_seconds', type='number', required=False, default=3, minimum=.25, maximum=8),
                    dict(name='poll_seconds', type='number', required=False, default=.25, minimum=.1, maximum=2)],
        effects='Standalone, opt-in observation only; at most 12 fresh captures. Requires request-only capture, verified geometry/provenance and the exact latest frame. No input or permission changes.',
        result=dict(protocol=RESULT_SCHEMA, receipt_field='observation_results',
                    verification='Sampled pre-overlay fingerprint change only; not transition completion, visual stability or successful action.',
                    failure_policy='Cancellation remains effective. A no-change timeout with valid samples completes the observation; acquisition failure blocks continuation until explicit fresh capture or Cancel.'))


def baseline_frame(service, frame_id):
    state = service.snapshot()
    frame = state['latest']
    stamp, geometry = frame.get('provenance', {}), frame.get('geometry', {})
    if state['pending'] or state['acquisitions_inflight']:
        raise ValueError('Another capture is pending/in flight; inspect it before observing a change.')
    if (stamp.get('frame_id') != frame_id or stamp.get('status') != 'acquired'
            or stamp.get('session_id') != state['session_id'] or stamp.get('lifecycle') != state['lifecycle']
            or 0 < stamp.get('request_generation', 0) <= service.rejected_generation or not frame.get('hash')
            or geometry.get('policy') != 'verified' or geometry.get('status') != 'bracketed'):
        raise ValueError('Baseline must be the exact latest valid frame with verified geometry and a capture fingerprint.')
    return copy.deepcopy(frame), state['request_generation']


def observe_screen_change(service, frame_id, timeout, interval, *, request, check, wait, monotonic=time.monotonic):
    """Run in the existing command worker; publication stays with the main loop.

    request(seconds_remaining, first) must return its exact generation while the
    service lock is held. Each sample requires that generation's publication.
    """
    started = monotonic()
    result = dict(schema_version=RESULT_SCHEMA, command=COMMAND, success=False, status='not_started',
                  condition_met=None, baseline_frame_id=frame_id, frame_id='', samples=0, requested_samples=0,
                  capture_generations=[],
                  timeout_seconds=timeout, poll_seconds=interval, max_samples=MAX_SAMPLES,
                  verification='sampled fingerprint only; transition completion and stability are unknown')
    owned_generation = None
    try:
        with service.lock:
            baseline, expected_generation = baseline_frame(service, frame_id)
            session, lifecycle = service.session_id, service.lifecycle
            result.update(capture_session_id=session, capture_lifecycle=lifecycle)
        deadline, next_sample = started + timeout, started
        while True:
            check()
            now = monotonic()
            with service.lock:
                state = service.snapshot()
                if service.session_id != session or service.lifecycle != lifecycle:
                    result.update(status='cancelled', cancelled=True, reason='Capture lifecycle changed.')
                    break
                if state['request_generation'] != expected_generation:
                    result.update(status='superseded', reason='A newer capture request owns observation; no retry.')
                    break
                if owned_generation is not None:
                    failure = state['current_failure']
                    if failure and failure['generation'] == owned_generation:
                        result.update(status='capture_failed', reason=failure['code'])
                        break
                    completion = state['last_completion']
                    frame = state['latest']
                    stamp = frame.get('provenance', {})
                    if (completion.get('generation') == owned_generation
                            and completion.get('frame_id') == stamp.get('frame_id')
                            and stamp.get('request_generation') == owned_generation):
                        result['samples'] += 1
                        result['frame_id'] = stamp['frame_id']
                        if frame.get('geometry') != baseline['geometry'] or not frame.get('hash'):
                            result.update(status='incomparable', reason='Target/geometry changed or fingerprint unavailable; inspect the new frame.')
                            break
                        if frame['hash'] != baseline['hash']:
                            result.update(success=True, status='changed', condition_met=True)
                            break
                        owned_generation = None
                        next_sample = now + interval
                if owned_generation is None:
                    if now >= deadline or (result['samples'] and next_sample >= deadline):
                        result.update(success=bool(result['samples']), status='timeout', condition_met=False if result['samples'] else None)
                        break
                    if result['requested_samples'] >= MAX_SAMPLES:
                        result.update(success=True, status='sample_limit', condition_met=False)
                        break
                    if now >= next_sample:
                        check()
                        owned_generation = request(max(.001, deadline-now), result['requested_samples'] == 0)
                        if not owned_generation:
                            result.update(status='capture_disabled', reason='Demand capture unavailable; no settings changed.')
                            break
                        expected_generation = owned_generation
                        result['capture_generations'].append(owned_generation)
                        result['requested_samples'] += 1
                elif now >= deadline:
                    # Preserve the ordinary terminal capture failure and stale-frame fence.
                    service._fail_request('observation_deadline_exceeded')
                    result.update(status='capture_failed', reason='No published frame before observation deadline.')
                    break
            wait(min(.02, max(.001, deadline-monotonic())))
    except WorkCancelled as error:
        result.update(status='cancelled', cancelled=True, reason=str(error))
    except ValueError as error:
        result.update(reason=str(error))
    finally:
        if owned_generation is not None:
            service.cancel_request(owned_generation, 'bounded observation ended')
        result['elapsed_seconds'] = round(max(0, monotonic()-started), 3)
    return result
