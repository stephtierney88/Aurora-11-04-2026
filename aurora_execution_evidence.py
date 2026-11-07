"""Request-local, bounded evidence. No credentials, bodies, URLs or global last-* joins."""
import copy
from contextlib import contextmanager
from contextvars import ContextVar
import re
import threading


_current = ContextVar('aurora_transport_evidence', default=None)
SCHEMA = 'aurora_transport_evidence_v1'
MAX_ATTEMPTS = 4
ATTEMPT_FIELDS = ('ordinal', 'transport', 'auth_mode', 'wire_model', 'wire_reasoning_effort',
                  'wire_service_tier', 'http_response_observed', 'http_status', 'provider_response_id',
                  'provider_request_id', 'provider_model', 'provider_reported_effort',
                  'provider_reported_service_tier', 'provider_response_status')
TOP_FIELDS = ('schema', 'scope', 'instrumented', 'worker_entered', 'worker_failed', 'observation_closed',
              'controller_selected_effort', 'configuration_update_sent', 'attempts_omitted')
RECEIPT_FAMILIES = ('setting_results', 'lock_results', 'settings_transaction_receipts', 'inference_plan_results',
                    'default_profile_results', 'pending_command_results', 'history_command_results',
                    'retrieval_results', 'goal_file_results', 'memory_command_results', 'task_control_results',
                    'task_budget_results', 'observation_results')


def code(value):
    """Opaque identifiers only; reject credential-like strings rather than truncate them."""
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', value):
        return None
    if value.lower().startswith(('sk-', 'ghp_', 'github_pat_', 'bearer', 'http:', 'https:')):
        return None
    return value


def scalar_fields(value, keys):
    value = value if isinstance(value, dict) else {}
    result = {}
    for key in keys:
        item = value.get(key)
        if item is None:
            result[key] = item
        elif key in {'instrumented', 'worker_entered', 'worker_failed', 'observation_closed', 'configuration_update_sent', 'http_response_observed'}:
            result[key] = item if type(item) is bool else None
        elif key in {'ordinal', 'http_status', 'attempts_omitted'}:
            result[key] = item if type(item) is int and 0 <= item <= 1000000 else None
        elif isinstance(item, str) and code(item) is not None:
            result[key] = item
    return result


def transport_snapshot(value):
    """Re-allowlist imported/exported evidence; keep old exports explicitly unknown."""
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        return {}
    result = scalar_fields(value, TOP_FIELDS)
    attempts = value.get('attempts') if isinstance(value.get('attempts'), list) else []
    result['attempts'] = [scalar_fields(row, ATTEMPT_FIELDS) for row in attempts[:MAX_ATTEMPTS] if isinstance(row, dict)]
    return result


class TransportEvidence:
    """A worker may publish diagnostics until the owning turn closes observation.

    A cancelled worker may drain afterward, but can never mutate frozen history.
    Zero attempts means no dispatch was observed, not proof of no network;
    cancellation can close observation before a child's phase arrives.
    """
    def __init__(self, payload, selection=None):
        self.lock = threading.Lock()
        selected = (selection or {}).get('effective_effort')
        if selected is None:
            selected = payload.get('reasoning_effort') or (payload.get('reasoning') or {}).get('effort')
        self.data = dict(schema=SCHEMA, scope='inference_transport_only', instrumented=False, worker_entered=False, worker_failed=False,
                         observation_closed=False, controller_selected_effort=code(selected),
                         configuration_update_sent=bool((selection or {}).get('configuration_update_sent', False)),
                         attempts=[], attempts_omitted=0)

    def update(self, **values):
        with self.lock:
            if not self.data['observation_closed']:
                self.data.update(values)

    def attempt(self, payload, transport, auth_mode):
        with self.lock:
            if self.data['observation_closed']:
                return
            if len(self.data['attempts']) >= MAX_ATTEMPTS:
                self.data['attempts_omitted'] += 1
                return
            self.data['attempts'].append(dict(ordinal=len(self.data['attempts'])+1, transport=transport,
                auth_mode=auth_mode, wire_model=code(payload.get('model')),
                wire_reasoning_effort=code(payload.get('reasoning_effort') or (payload.get('reasoning') or {}).get('effort')),
                wire_service_tier=code(payload.get('service_tier')), http_response_observed=False))

    def response(self, *, status=None, headers=None, body=None):
        with self.lock:
            if self.data['observation_closed'] or not self.data['attempts'] or self.data['attempts_omitted']:
                return
            row = self.data['attempts'][-1]
            row['http_response_observed'] = True
            if type(status) is int and 100 <= status <= 599:
                row['http_status'] = status
            if hasattr(headers, 'get'):
                row['provider_request_id'] = code(headers.get('x-request-id'))
            if isinstance(body, dict):
                row.update(provider_response_id=code(body.get('id')), provider_model=code(body.get('model')),
                    provider_reported_service_tier=code(body.get('service_tier')),
                    provider_response_status=code(body.get('status')))
                reasoning = body.get('reasoning')
                row['provider_reported_effort'] = code(reasoning.get('effort')) if isinstance(reasoning, dict) else None

    def snapshot(self, *, close=False):
        with self.lock:
            if close:
                self.data['observation_closed'] = True
            return transport_snapshot(self.data)


@contextmanager
def observe_transport(evidence):
    token = _current.set(evidence)
    evidence.update(worker_entered=True)
    try:
        yield
    except BaseException:
        evidence.update(worker_failed=True)
        raise
    finally:
        _current.reset(token)


def instrumented():
    if _current.get() is not None:
        _current.get().update(instrumented=True)


def attempt(payload, transport, auth_mode):
    if _current.get() is not None:
        _current.get().attempt(payload, transport, auth_mode)


def response(*, status=None, headers=None, body=None):
    if _current.get() is not None:
        _current.get().response(status=status, headers=headers, body=body)


def http_response(value):
    """Metadata only; diagnostic parse errors never alter transport behavior."""
    try:
        response(status=value.status_code, headers=getattr(value, 'headers', None))
        if value.status_code == 200:
            response(body=value.json())
    except Exception:
        pass


def receipt_summary(receipt):
    """Count typed local handler results, never preserve arguments/values/error text."""
    families = []
    for name in RECEIPT_FAMILIES:
        rows = receipt.get(name)
        if not isinstance(rows, list):
            continue
        statuses = {}
        # Counts beyond this inspection cap remain omitted, not silently absent.
        success = failed = unknown = 0
        for row in rows[:64]:
            status = row.get('status') if isinstance(row, dict) else None
            status = status if isinstance(status, str) and status in {'success', 'failed', 'failed_uncertain', 'cancelled', 'blocked', 'applied',
                'queried', 'changed', 'timeout', 'sample_limit', 'incomparable', 'superseded', 'capture_failed', 'not_started'} else 'unknown'
            statuses[status] = statuses.get(status, 0) + 1
            flag = row.get('success') if isinstance(row, dict) else None
            success += flag is True
            failed += flag is False
            unknown += flag is not True and flag is not False
        families.append(dict(family=name, count=len(rows), inspected=min(len(rows), 64), omitted=max(0, len(rows)-64),
                             success_true=success, success_false=failed, success_unknown=unknown, statuses=statuses))
    return dict(schema='aurora_receipt_evidence_v1', families=families,
                meaning='Local handler reports; independent outcome verification remains unknown.')


def receipt_snapshot(value):
    if not isinstance(value, dict) or value.get('schema') != 'aurora_receipt_evidence_v1':
        return {}
    # Rebuild the small known shape without copying arbitrary nested fields.
    result = dict(schema=value['schema'], families=[], meaning='Local handler reports; independent outcome verification remains unknown.')
    families = value.get('families') if isinstance(value.get('families'), list) else []
    for row in families[:len(RECEIPT_FAMILIES)]:
        if not isinstance(row, dict) or row.get('family') not in RECEIPT_FAMILIES:
            continue
        clean = {'family': row['family']}
        for key in ('count', 'inspected', 'omitted', 'success_true', 'success_false', 'success_unknown'):
            if type(row.get(key)) is int and row[key] >= 0:
                clean[key] = row[key]
        statuses = row.get('statuses') if isinstance(row.get('statuses'), dict) else {}
        clean['statuses'] = {key: count for key, count in statuses.items()
                             if key in {'success', 'failed', 'failed_uncertain', 'cancelled', 'blocked', 'applied', 'queried',
                             'changed', 'timeout', 'sample_limit', 'incomparable', 'superseded', 'capture_failed', 'not_started', 'unknown'}
                             and type(count) is int and count >= 0}
        result['families'].append(clean)
    return copy.deepcopy(result)
