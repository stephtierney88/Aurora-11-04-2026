"""Pure bounded execution-inspection projection; no UI, disk or runtime actions."""
import copy
import json
import re
from aurora_task_continuation import TaskProgress
from aurora_capture_artifacts import FIELDS as ARTIFACT_FIELDS
from aurora_execution_evidence import transport_snapshot, receipt_snapshot


LIMIT = 64
NOTICE = ("Read-only frozen export. Load latest export explicitly to follow progress or switch tasks. "
          "Linked details show the latest retained record in this snapshot, not its state at the selected event. "
          "Select a request to check its local screenshot file now. That check is separate from the frozen export. "
          "Execution receipts and file integrity are not verification of the intended result. No replay or undo.")
FIELDS = {
    'events': ('sequence', 'kind', 'identity', 'observed_at_seconds', 'status', 'frame_id',
               'capture_request_generation', 'observation_generation'),
    'commands': ('command_batch_id', 'origin_request_id', 'receipt_id', 'admitted_at', 'receipt_at',
                 'status', 'binding_count', 'binding_names_omitted', 'executed_count', 'failed_count',
                 'blocked_count', 'cancelled_count', 'observation_generation', 'required_request_generation',
                 'observation_requested_at', 'frame_id', 'frame_observed_at', 'capture_request_generation',
                 'frame_prepared_at', 'frame_request_id', 'readback_prepared_at', 'readback_request_id'),
    'requests': ('inference_request_id', 'phase', 'model', 'frame_id', 'request_started', 'result_phase', 'provider_model'),
}
NESTED = {
    'latency_ms': ('admission_to_receipt', 'observation_wait', 'receipt_to_frame_observed',
                   'receipt_to_readback_prepared', 'frame_observed_to_request_prepared', 'preparation',
                   'prepared_to_submitted', 'submitted_to_response', 'submitted_to_terminal'),
    'phase_times': tuple(TaskProgress.PHASES),
    'prepared_settings': ('reasoning_effort', 'service_tier', 'configured_transport', 'configured_auth', 'review_turn', 'critique_turn'),
    'frame_provenance': ('status', 'frame_id', 'session_id', 'sequence', 'lifecycle', 'request_generation',
                         'acquired_start_epoch', 'acquired_end_epoch', 'acquired_start_monotonic', 'acquired_end_monotonic'),
    'reported_usage': ('input_tokens', 'output_tokens', 'total_tokens'),
    'frame_artifact': ARTIFACT_FIELDS,
}


def inspection_snapshot(state):
    """Freeze an allowlisted single-export projection; never join global last-* data."""
    state = state if isinstance(state, dict) else {}
    def mapping(value):
        return value if isinstance(value, dict) else {}
    continuation = mapping(state.get('continuation'))
    task = mapping(continuation.get('active_task'))
    progress = mapping(task.get('progress'))
    result = dict(schema='aurora_execution_inspector_v1', notice=NOTICE,
                  task=TaskProgress.safe_fields(task, ('task_id', 'status', 'stop_reason', 'turns', 'elapsed_seconds', 'max_turns', 'max_seconds')),
                  mode=continuation.get('mode') if continuation.get('mode') in ('legacy', 'bounded') else 'unknown',
                  retention=TaskProgress.safe_fields(progress, ('events_total', 'events_evicted', 'batches_evicted', 'requests_evicted')),
                  collections={}, display_omitted={}, available=False)
    timestamp = state.get('timestamp')
    result['source_export'] = {'timestamp': timestamp if isinstance(timestamp, str) and re.fullmatch(
        r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?', timestamp) else None}
    if not task.get('task_id') or progress.get('schema') != 'aurora_task_progress_v1':
        result['unavailable_reason'] = 'No bounded task ledger in this export. Legacy operation remains available.'
        return result
    for name, fields in FIELDS.items():
        source = progress.get(name)
        if not isinstance(source, list):
            result['unavailable_reason'] = 'Detailed progress was not retained in this export.'
            return result
        selected = []
        identities = set()
        for value in source[-LIMIT:]:
            if not isinstance(value, dict):
                continue
            row = TaskProgress.safe_fields(value, fields)
            identity_key = {'events': 'sequence', 'commands': 'command_batch_id', 'requests': 'inference_request_id'}[name]
            identity = row.get(identity_key)
            valid = (type(identity) is int and identity > 0) if name == 'events' else (isinstance(identity, str) and bool(identity))
            if not valid or identity in identities:
                result['unavailable_reason'] = 'Invalid or duplicate ledger identities; no ambiguous joins shown.'
                return result
            identities.add(identity)
            if name != 'events':
                if 'transport_evidence' in value:
                    row['transport_evidence'] = transport_snapshot(value['transport_evidence'])
                if 'receipt_evidence' in value:
                    row['receipt_evidence'] = receipt_snapshot(value['receipt_evidence'])
                for key, nested_fields in NESTED.items():
                    if key in value:
                        row[key] = TaskProgress.safe_fields(value[key], nested_fields)
                for key in ('binding_names', 'readback_batch_ids', 'frame_batch_ids'):
                    if isinstance(value.get(key), list):
                        row[key] = [item[:160] for item in value[key][:LIMIT] if isinstance(item, str)]
            selected.append(row)
        result['collections'][name] = selected
        result['display_omitted'][name] = len(source) - len(selected)
    result['available'] = True
    return result


def inspection_detail(snapshot, collection, identity):
    """Exact joins only; absence and truncation never imply a negative outcome."""
    if not snapshot.get('available'):
        return {'unknown': snapshot.get('unavailable_reason', 'No snapshot')}
    rows = snapshot['collections']
    field = {'events': 'sequence', 'commands': 'command_batch_id', 'requests': 'inference_request_id'}[collection]
    selected = next((row for row in rows[collection] if str(row.get(field)) == str(identity)), None)
    if selected is None:
        return {'unknown': 'Selected record is missing or evicted.'}
    commands = {r['command_batch_id']: r for r in rows['commands']}
    requests = {r['inference_request_id']: r for r in rows['requests']}
    command, request = None, None
    if collection == 'commands':
        command = selected
    elif collection == 'requests':
        request = selected
    elif selected.get('kind') in {'command_admitted', 'command_receipt', 'observation_requested', 'frame_observed'}:
        command = commands.get(selected.get('identity'))
    elif str(selected.get('kind', '')).startswith('model_'):
        request = requests.get(selected.get('identity'))
    linked = {}
    if command:
        for key in ('origin_request_id', 'frame_request_id', 'readback_request_id'):
            if command.get(key):
                linked[key] = requests.get(command[key]) or {'inference_request_id': command[key], 'unknown': 'Request not retained.'}
    if request:
        for key in ('readback_batch_ids', 'frame_batch_ids'):
            linked[key] = [commands.get(i) or {'command_batch_id': i, 'unknown': 'Batch not retained.'} for i in request.get(key, [])]
    return copy.deepcopy(dict(task_id=snapshot['task']['task_id'], selected_event_or_record=selected,
        latest_command_in_snapshot=command, latest_request_in_snapshot=request, linked_records=linked,
        evidence=dict(verification='unknown; no independent outcome proof in this ledger',
            transport='Attempts are observed local HTTP dispatch boundaries, not proof of bytes sent or provider acceptance. Auth/catalog traffic is excluded; zero attempts means none observed.',
            provider_effort='Prepared/controller selections are not provider confirmation; per-attempt reported fields may echo request-level settings, especially with configuration updates.',
            screenshot_pixels='not displayed; optional file check verifies source bytes only',
            provider_call_id='Per-attempt IDs when reported; otherwise unknown. inference_request_id is Aurora local identity.'),
        retention=snapshot['retention'], display_omitted=snapshot['display_omitted']))


def normalize_inspection(snapshot):
    """Re-project a saved view; preserve explicit omissions without trusting extras."""
    if not isinstance(snapshot, dict) or snapshot.get('schema') != 'aurora_execution_inspector_v1' or snapshot.get('available') is not True:
        raise ValueError('No supported bounded inspection snapshot.')
    collections = snapshot.get('collections')
    if not isinstance(collections, dict) or any(not isinstance(collections.get(key), list) or len(collections[key]) > LIMIT for key in FIELDS):
        raise ValueError('Invalid or oversized inspection collections.')
    if any(not isinstance(snapshot.get(key), dict) for key in ('task', 'retention', 'display_omitted')):
        raise ValueError('Invalid inspection metadata.')
    task = dict(snapshot.get('task') or {})
    progress = dict(snapshot.get('retention') or {})
    progress.update(collections, schema='aurora_task_progress_v1')
    task['progress'] = progress
    source = snapshot.get('source_export') if isinstance(snapshot.get('source_export'), dict) else {}
    clean = inspection_snapshot({'timestamp': source.get('timestamp'),
        'continuation': {'mode': snapshot.get('mode'), 'active_task': task}})
    if not clean['available']:
        raise ValueError('Ambiguous inspection identities.')
    omitted = snapshot.get('display_omitted') or {}
    for key in FIELDS:
        count = omitted.get(key, 0)
        if type(count) is not int or not 0 <= count <= 1000000000:
            raise ValueError('Invalid inspection omission count.')
        clean['display_omitted'][key] = count
    return clean
