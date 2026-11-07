"""Optional durable input receipts and explicit recovery; never auto-replay.

One runtime owns the file lease. Atomic snapshots precede queue admission and
request submission; a crash leaves held/uncertain input for operator inspection.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid

SCHEMA = 'aurora_input_recovery_v1'
COMPACT_SCHEMA = 'aurora_input_recovery_v2'
RESULT_SCHEMA = 'aurora_memory_command_result_v1'
COMMANDS = {'SHOW_INPUT_RECOVERY', 'CANCEL_QUEUED_INPUT', 'RETRY_INPUT',
            'SHOW_INPUT_RECOVERY_STATUS', 'ACK_INPUT_RECOVERY_DIAGNOSTIC',
            'PREVIEW_INPUT_RECOVERY_ARCHIVE',
            'PREVIEW_INPUT_RECOVERY_COMPACTION', 'COMPACT_INPUT_RECOVERY',
            'PREVIEW_INPUT_RECONCILIATION', 'RECONCILE_INPUT_DELIVERY'}
PHASES = {'queued', 'claimed', 'preparing', 'prepared', 'submitted', 'responded',
          'failed', 'cancelled', 'not_sent', 'held', 'uncertain'}
ACTIVE = {'claimed', 'preparing', 'prepared', 'submitted'}
MAX_BYTES = 8 * 1024 * 1024
ARCHIVE_SEGMENT_SCHEMA = 'aurora_input_recovery_segment_v1'
ARCHIVE_PREVIEW_SCHEMA = 'aurora_input_recovery_archive_preview_v1'
ARCHIVE_SEGMENT_MAX_BYTES = 4 * 1024 * 1024
ARCHIVE_SEGMENT_MAX_RECORDS = 10000


def is_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def text_digest(text):
    return hashlib.sha256(text.encode('utf-8', errors='surrogatepass')).hexdigest()


def parse_arguments(name, args):
    name, args = name.upper(), list(args)
    if any(not isinstance(arg, str) or '\x00' in arg for arg in args):
        raise ValueError('Recovery arguments must be text without NUL.')
    if name == 'SHOW_INPUT_RECOVERY_STATUS':
        if args:
            raise ValueError('SHOW_INPUT_RECOVERY_STATUS takes no arguments.')
        return {}
    if name == 'PREVIEW_INPUT_RECOVERY_ARCHIVE':
        if len(args)>1:
            raise ValueError('Use PREVIEW_INPUT_RECOVERY_ARCHIVE([limit=1000]).')
        limit = int(args[0]) if args else 1000
        if not 1 <= limit <= ARCHIVE_SEGMENT_MAX_RECORDS:
            raise ValueError('Archive preview limit is 1..10000 compacted identities.')
        return dict(limit=limit)
    if name == 'ACK_INPUT_RECOVERY_DIAGNOSTIC':
        if len(args) != 1 or not is_digest(args[0]):
            raise ValueError('Use the exact diagnostic version from SHOW_INPUT_RECOVERY_STATUS.')
        return dict(version=args[0])
    if name in {'PREVIEW_INPUT_RECONCILIATION','RECONCILE_INPUT_DELIVERY'}:
        apply=name=='RECONCILE_INPUT_DELIVERY'
        if len(args)!=(3 if apply else 2) or not all(is_digest(arg) for arg in args):
            raise ValueError('Use exact entry_id, version from SHOW_INPUT_RECOVERY; apply also requires the preview evidence_version.')
        return dict(zip(('entry_id','version','evidence_version'),args))
    if name in {'PREVIEW_INPUT_RECOVERY_COMPACTION', 'COMPACT_INPUT_RECOVERY'}:
        apply = name == 'COMPACT_INPUT_RECOVERY'
        if (apply and len(args) != 4) or (not apply and len(args) > 2):
            raise ValueError('Use PREVIEW_INPUT_RECOVERY_COMPACTION([keep_terminal, limit]) then its exact apply_command.')
        keep, limit = int(args[0]) if args else 20, int(args[1]) if len(args) > 1 else 100
        if not 0 <= keep <= 1000 or not 1 <= limit <= 100:
            raise ValueError('Compaction keep_terminal is 0..1000; limit is 1..100.')
        options = dict(keep_terminal=keep, limit=limit)
        if apply:
            if not is_digest(args[2]) or args[3] != 'discard_text':
                raise ValueError('Apply requires the preview version and explicit discard_text acknowledgement.')
            options['version'] = args[2]
        return options
    if name == 'SHOW_INPUT_RECOVERY':
        if len(args) > 2:
            raise ValueError('Use SHOW_INPUT_RECOVERY([offset, limit]).')
        offset, limit = int(args[0]) if args else 0, int(args[1]) if len(args) > 1 else 30
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError('Recovery offset >= 0; limit 1..100.')
        return dict(offset=offset, limit=limit)
    if name not in COMMANDS or len(args) not in ({2, 3} if name == 'RETRY_INPUT' else {2}):
        raise ValueError('Use entry_id, version from SHOW_INPUT_RECOVERY; retry optionally accepts allow_uncertain.')
    if any(len(arg) != 64 or any(char not in '0123456789abcdef' for char in arg) for arg in args[:2]):
        raise ValueError('Use exact recovery entry_id and version hashes.')
    if len(args) == 3 and args[2] != 'allow_uncertain':
        raise ValueError('The optional retry acknowledgement is allow_uncertain.')
    result = dict(entry_id=args[0], version=args[1])
    if name == 'RETRY_INPUT':
        result['allow_uncertain'] = len(args) == 3
    return result


def describe_contract(name):
    if name.upper() == 'PREVIEW_INPUT_RECOVERY_ARCHIVE':
        return dict(parameter_validation='pre_dispatch', argument_style='positional',
            min_arguments=0, max_arguments=1, parameters=[dict(name='limit',type='integer',required=False)],
            effects='Preview a bounded immutable duplicate-protection segment without writing or activating it',
            semantics='Durable mode only. Default 1000, maximum 10000 compacted identities, sorted by identity hash. '
                      'Reports exact candidate byte digest/size and source version; no full text, files, eviction, migration or replay. '
                      'Savings are hypothetical. Archive activation and lookup remain unavailable.',
            result=dict(protocol=RESULT_SCHEMA, receipt_field='memory_command_results',
                        failure_policy='Failures stop the batch tail. Invalid or closed stores produce no candidate.'))
    if name.upper() in {'SHOW_INPUT_RECOVERY_STATUS', 'ACK_INPUT_RECOVERY_DIAGNOSTIC'}:
        apply = name.upper() == 'ACK_INPUT_RECOVERY_DIAGNOSTIC'
        return dict(parameter_validation='pre_dispatch', argument_style='positional',
            min_arguments=int(apply), max_arguments=int(apply),
            parameters=[dict(name='version', type='string', required=True)] if apply else [],
            effects='Mark one exact recovery diagnostic seen' if apply else 'Inspect recovery readiness without opening its store',
            semantics='Available in legacy and durable modes. Acknowledgement is operator-only and execution-unlocked; '
                      'it never clears failures, changes records/settings, authorizes retries or proves disk health. '
                      'Diagnostics are session-only; a new failure needs a new acknowledgement.',
            result=dict(protocol=RESULT_SCHEMA, receipt_field='memory_command_results',
                        failure_policy='Failures stop the batch tail; stale diagnostic versions change nothing.'))
    if name.upper() in {'PREVIEW_INPUT_RECONCILIATION','RECONCILE_INPUT_DELIVERY'}:
        apply=name.upper()=='RECONCILE_INPUT_DELIVERY'
        return dict(parameter_validation='pre_dispatch',argument_style='positional',
            min_arguments=3 if apply else 2,max_arguments=3 if apply else 2,
            parameters=[dict(name=key,type='string',required=True) for key in
                        (('entry_id','version','evidence_version') if apply else ('entry_id','version'))],
            effects='Reconcile unresolved recovery bookkeeping from exact terminal delivery receipts' if apply else 'Preview exact delivery receipt reconciliation without mutation',
            semantics='Durable mode only. Exact current attempt and turn; complete local receipt chain within a bounded log window. '
                      'Operator-only apply requires paused inference, idle model I/O, execution unlocked and unchanged entry/evidence. '
                      'Never sends input, restores context, executes actions or confirms remote cancellation. Missing/conflicting evidence stays unresolved.',
            result=dict(protocol=RESULT_SCHEMA,receipt_field='memory_command_results',
                        failure_policy='Failures stop the batch tail. Reinspect after uncertain writes; never retry model work automatically.'))
    if name.upper() in {'PREVIEW_INPUT_RECOVERY_COMPACTION', 'COMPACT_INPUT_RECOVERY'}:
        apply = name.upper() == 'COMPACT_INPUT_RECOVERY'
        return dict(parameter_validation='pre_dispatch', argument_style='positional',
            min_arguments=4 if apply else 0, max_arguments=4 if apply else 2,
            parameters=[dict(name=key, type='integer' if key in {'keep_terminal','limit'} else 'string', required=apply)
                        for key in (('keep_terminal','limit','version','discard_text') if apply else ('keep_terminal','limit'))],
            effects='Discard selected terminal recovery text; preserve deduplication hashes' if apply else 'Preview bounded recovery compaction without mutation',
            semantics='Durable mode only. Keeps newest eligible records by admission order, not date. At most 100 removals. Operator-only apply requires a fresh whole-store preview version and discard_text. Pending/failed/uncertain records stay. No log erasure or undo; no automatic eviction of deduplication hashes.',
            result=dict(protocol=RESULT_SCHEMA, receipt_field='memory_command_results',
                        failure_policy='Failures stop the batch tail; stale preview or disk failure leaves data unchanged.'))
    read = name.upper() == 'SHOW_INPUT_RECOVERY'
    return dict(parameter_validation='pre_dispatch', argument_style='positional',
        min_arguments=0 if read else 2, max_arguments=2 if name.upper() != 'RETRY_INPUT' else 3,
        parameters=[dict(name=key, type='integer' if read else 'string', required=not read and key != 'allow_uncertain') for key in
                    (('offset', 'limit') if read else ('entry_id', 'version', 'allow_uncertain') if name.upper() == 'RETRY_INPUT' else ('entry_id', 'version'))],
        effects='Inspect durable input' if read else 'Operator-only explicit queued input recovery',
        semantics='Durable mode only. Recovered input never auto-runs. Use fresh IDs/versions; active input requires Cancel work. Retry creates a fresh request; uncertain prior delivery needs allow_uncertain and idle model I/O.',
        result=dict(protocol=RESULT_SCHEMA, receipt_field='memory_command_results',
                    failure_policy='Failures stop the batch tail. No automatic resend or rollback of earlier effects.'))


def identity_key(identity):
    if not isinstance(identity, dict) or set(identity) != {'client_id', 'request_id', 'message_id'}:
        raise ValueError('Recovery requires complete input identity.')
    if any(not isinstance(v, str) or not v or len(v) > 512 for v in identity.values()):
        raise ValueError('Invalid input identity.')
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


class RecoveryDiagnostics:
    """Session-only evidence. Seeing an error is independent of fixing it or retrying."""
    def __init__(self):
        self.lock = threading.RLock()
        self.epoch, self.sequence = uuid.uuid4().hex, 0
        self.diagnostic, self.last_write = None, 'not_observed'

    def failure(self, operation, error):
        if operation not in {'open', 'write', 'delivery'}:
            raise ValueError('Unknown recovery diagnostic operation.')
        # Never export exception messages, paths, credentials or retained text.
        kind = next((k.__name__ for k in (PermissionError, OSError, ValueError, RuntimeError)
                     if isinstance(error, k)), 'Exception')
        with self.lock:
            self.sequence += 1
            self.diagnostic = dict(version=text_digest(f'{self.epoch}:{self.sequence}'),
                operation=operation, error_type=kind, observed_at_epoch=time.time(), acknowledged=False)
            if operation in {'write', 'delivery'}:
                self.last_write = 'failed'

    def wrote(self):
        with self.lock:
            self.last_write = 'succeeded'

    def snapshot(self):
        with self.lock:
            return dict(diagnostic=copy.deepcopy(self.diagnostic), last_write=self.last_write)

    def acknowledge(self, version):
        with self.lock:
            if not self.diagnostic or version != self.diagnostic['version']:
                raise ValueError('Recovery diagnostic changed/reloaded; inspect the current version.')
            changed = not self.diagnostic['acknowledged']
            self.diagnostic['acknowledged'] = True
            return changed


def recovery_readiness(mode, store, diagnostics, *, startup_mode, startup_source):
    """Read cached evidence only; never acquire a lease, probe disk or modify input."""
    state = diagnostics.snapshot()
    summary = store.summary() if store is not None else {}
    opened = bool(store is not None and store.lease is not None)
    phases = summary.get('phases', {})
    return dict(schema_version='aurora_input_recovery_readiness_v1', effective_mode=mode,
        startup_mode=startup_mode, startup_source=startup_source,
        store_state='open' if opened else 'closed' if store is not None else 'not_open',
        records_available=mode == 'durable' and opened,
        held=phases.get('held') if opened else None, uncertain=phases.get('uncertain') if opened else None,
        active=sum(phases.get(p, 0) for p in ACTIVE) if opened else None, summary=summary, **state,
        persistence_scope='identified operator inbox input; shell/audio not covered',
        note='Open store is not a disk-health guarantee. Acknowledgement only marks a diagnostic seen. '
             'No automatic replay; uncertain delivery still needs explicit review/retry.')


class InputRecovery:
    def __init__(self, path, *, max_rows=1000, max_tombstones=10000, diagnostics=None):
        self.diagnostics = diagnostics
        self.path, self.max_rows = Path(path), max_rows
        self.schema, self.tombstones, self.max_tombstones = SCHEMA, {}, max_tombstones
        self.lock, self.epoch, self.rows = threading.RLock(), uuid.uuid4().hex, {}
        self.serialized_bytes = len(json.dumps(dict(schema_version=SCHEMA, rows={})).encode())
        self.lease = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.with_suffix('.lock').open('a+b')
        try:
            handle.seek(0, 2)
            if not handle.tell():
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lease = handle
            if self.path.exists():
                with self.path.open('rb') as source:
                    data = source.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError('Recovery document exceeds size limit.')
                def unique_pairs(items):
                    result = {}
                    for key, value in items:
                        if key in result:
                            raise ValueError('Duplicate recovery JSON field.')
                        result[key] = value
                    return result
                saved = json.loads(data, object_pairs_hook=unique_pairs)
                self.rows = self.validate(saved)
                self.schema = saved['schema_version']
                self.tombstones = copy.deepcopy(saved.get('tombstones', {}))
                self.serialized_bytes = len(json.dumps(saved, ensure_ascii=True, allow_nan=False).encode())
                changed = False
                for row in self.rows.values():
                    if row['phase'] == 'queued' or row['phase'] in ACTIVE:
                        row['phase'] = 'held' if row['phase'] == 'queued' else 'uncertain'
                        row['revision'] += 1
                        changed = True
                if changed:
                    self._publish(self.rows)
        except Exception:
            handle.close()
            self.lease = None
            raise

    def close(self):
        with self.lock:
            if self.lease is not None:
                self.lease.close()
                self.lease = None

    def validate(self, saved):
        if not isinstance(saved, dict) or saved.get('schema_version') not in {SCHEMA, COMPACT_SCHEMA}:
            raise ValueError('Invalid recovery document.')
        expected = {'schema_version', 'rows'} | ({'tombstones'} if saved['schema_version'] == COMPACT_SCHEMA else set())
        if set(saved) != expected or not isinstance(saved['rows'], dict):
            raise ValueError('Invalid recovery document fields.')
        tombstones = saved.get('tombstones', {})
        if not isinstance(tombstones, dict) or len(tombstones) > self.max_tombstones or set(tombstones) & set(saved['rows']):
            raise ValueError('Invalid or full recovery deduplication index.')
        for key, tombstone in tombstones.items():
            if (not is_digest(key) or not isinstance(tombstone, dict)
                    or set(tombstone) != {'text_sha256','text_chars','phase','attempt'}
                    or not is_digest(tombstone['text_sha256']) or type(tombstone['text_chars']) is not int
                    or not 1 <= tombstone['text_chars'] <= 64000 or tombstone['phase'] not in {'responded','cancelled'}
                    or type(tombstone['attempt']) is not int or tombstone['attempt'] < 1):
                raise ValueError('Invalid recovery deduplication record.')
        if len(saved['rows']) > self.max_rows:
            raise ValueError('Too many retained recovery inputs.')
        attempts = set()
        for key, row in saved['rows'].items():
            if not isinstance(row, dict) or set(row) != {'original_identity', 'identity', 'text', 'phase', 'revision', 'attempt', 'request_started', 'turn_id', 'sequence'}:
                raise ValueError('Invalid recovery row fields.')
            if key != identity_key(row['original_identity']):
                raise ValueError('Recovery identity mismatch.')
            attempt_key = identity_key(row['identity'])
            if attempt_key in attempts:
                raise ValueError('Duplicate recovery attempt identity.')
            attempts.add(attempt_key)
            if row['phase'] not in PHASES or type(row['revision']) is not int or row['revision'] < 1 or type(row['attempt']) is not int or row['attempt'] < 1:
                raise ValueError('Invalid recovery state/version.')
            if type(row['request_started']) is not bool or type(row['sequence']) is not int or row['sequence'] < 0 or not isinstance(row['turn_id'], str):
                raise ValueError('Invalid delivery evidence.')
            if not isinstance(row['text'], str) or not row['text'] or len(row['text']) > 64000:
                raise ValueError('Recovery input must contain 1..64000 characters.')
        return copy.deepcopy(saved['rows'])

    def _publish(self, rows, *, tombstones=None):
        try:
            self._publish_snapshot(rows, tombstones=tombstones)
        except Exception as error:
            if self.diagnostics is not None:
                self.diagnostics.failure('write', error)
            raise
        if self.diagnostics is not None:
            self.diagnostics.wrote()

    def _publish_snapshot(self, rows, *, tombstones=None):
        if self.lease is None:
            raise RuntimeError('Recovery store is closed.')
        tombstones = self.tombstones if tombstones is None else tombstones
        schema = COMPACT_SCHEMA if tombstones or self.schema == COMPACT_SCHEMA else SCHEMA
        document = dict(schema_version=schema, rows=rows)
        if schema == COMPACT_SCHEMA:
            document['tombstones'] = tombstones
        self.validate(document)
        data = json.dumps(document, ensure_ascii=True, allow_nan=False).encode()
        if len(data) > MAX_BYTES:
            raise ValueError('Recovery document full; inspect retained inputs.')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.aurora-input-', suffix='.tmp', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None  # Replace consumed it; do not fail after commit trying to unlink it again.
            self.rows, self.tombstones, self.schema = rows, tombstones, schema
            self.serialized_bytes = len(data)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def version(self, key, row):
        return hashlib.sha256(json.dumps([self.epoch, key, row], sort_keys=True).encode()).hexdigest()

    def snapshot(self, offset=0, limit=30):
        with self.lock:
            total = len(self.rows)
            rows = [dict(copy.deepcopy(row), entry_id=key, version=self.version(key, row)) for key, row in list(self.rows.items())[offset:offset+limit]]
            return dict(total=total, compacted=len(self.tombstones), offset=offset, omitted_before=min(offset,total),
                        omitted=max(0, total-min(offset, total)-limit), entries=rows)

    def summary(self):
        with self.lock:
            return dict(total=len(self.rows), compacted=len(self.tombstones),
                        text_capacity=self.max_rows, deduplication_capacity=self.max_tombstones,
                        capacity=self.capacity_summary(),
                        schema_version=self.schema,
                        phases={phase: sum(row['phase'] == phase for row in self.rows.values()) for phase in sorted(PHASES)})


    def capacity_summary(self):
        """Cached size plus live counts; no disk probe, serialization or eviction."""
        with self.lock:
            eligible = sum(row['phase'] == 'responded' or
                           (row['phase'] == 'cancelled' and not row['request_started']) for row in self.rows.values())
            slots = max(0, self.max_rows-len(self.rows))
            index_slots = max(0, self.max_tombstones-len(self.tombstones))
            bytes_remaining = max(0, MAX_BYTES-self.serialized_bytes)
            return dict(schema_version='aurora_input_recovery_capacity_v1',
                retained_used=len(self.rows), retained_limit=self.max_rows, retained_available=slots,
                deduplication_used=len(self.tombstones), deduplication_limit=self.max_tombstones,
                deduplication_available=index_slots,
                snapshot_bytes=self.serialized_bytes, snapshot_byte_limit=MAX_BYTES,
                snapshot_bytes_available=bytes_remaining,
                eligible_terminal=eligible, protected_payloads=len(self.rows)-eligible,
                compaction_slots=min(eligible,index_slots),
                compaction_blocked_by_index=eligible>index_slots,
                new_input_capacity='retained_limit' if not slots else 'byte_limit' if not bytes_remaining else 'payload_dependent',
                index_policy='retain_all_stop_at_limit', archive_rollover_available=False,
                note='Snapshot bytes are the canonical loaded/published encoding, not disk free space. '
                     'Message size and later state transitions can still exceed the byte limit. '
                     'A full deduplication index blocks further compaction, not use of remaining retained-input slots. '
                     'Original-envelope identities are never silently evicted; no automatic archive or replay.')

    def admit(self, text, identity):
        with self.lock:
            key = identity_key(identity)
            if not isinstance(text, str) or not 1 <= len(text) <= 64000:
                raise ValueError('Recovery input must contain 1..64000 characters.')
            if key in self.tombstones:
                tombstone = self.tombstones[key]
                if tombstone['text_chars'] != len(text) or tombstone['text_sha256'] != text_digest(text):
                    raise ValueError('Compacted input identity already belongs to different text.')
                return False
            if key in self.rows:
                if self.rows[key]['text'] != text:
                    raise ValueError('Input identity already belongs to different text.')
                return False
            rows = copy.deepcopy(self.rows)
            if len(rows) >= self.max_rows:
                raise ValueError('Recovery store full; retained identities were preserved. No input was admitted.')
            rows[key] = dict(original_identity=copy.deepcopy(identity), identity=copy.deepcopy(identity), text=str(text),
                phase='queued', revision=1, attempt=1, request_started=False, turn_id='', sequence=0)
            self._publish(rows)
            return True

    def compaction_preview(self, keep_terminal=20, limit=100):
        """Select by original admission order; never discard unresolved payloads."""
        if type(keep_terminal) is not int or not 0 <= keep_terminal <= 1000 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Invalid compaction bounds.')
        with self.lock:
            eligible = [(key,row) for key,row in self.rows.items()
                        if row['phase'] == 'responded' or (row['phase'] == 'cancelled' and not row['request_started'])]
            available = max(0,len(eligible)-keep_terminal)
            capacity = max(0,self.max_tombstones-len(self.tombstones))
            selected = eligible[:min(available, limit, capacity)]
            version = hashlib.sha256(json.dumps([self.epoch,self.schema,list(self.rows.items()),
                self.tombstones,keep_terminal,limit,self.max_tombstones], sort_keys=True).encode()).hexdigest()
            entries = [dict(entry_id=key, phase=row['phase'], attempt=row['attempt'],
                            text_chars=len(row['text']), text_sha256=text_digest(row['text'])) for key,row in selected]
            if not eligible:
                selection_reason = 'no_eligible_terminal_inputs'
            elif not available:
                selection_reason = 'retention_floor'
            elif not capacity:
                selection_reason = 'deduplication_limit'
            elif len(entries) < available:
                selection_reason = 'batch_and_index_limit' if capacity==limit else 'deduplication_limit' if capacity<limit else 'batch_limit'
            else:
                selection_reason = 'all_candidates_selected'
            return dict(version=version,keep_terminal=keep_terminal,limit=limit,eligible=len(eligible),
                selected=entries,selected_count=len(entries),text_chars=sum(r['text_chars'] for r in entries),
                deduplication_available=capacity,capacity_blocked=available>capacity,
                selection_reason=selection_reason,capacity=self.capacity_summary(),
                remaining_candidates=available-len(entries),
                apply_command=f'COMPACT_INPUT_RECOVERY({keep_terminal},{limit},{version},discard_text)',
                note='Removes selected recovery text only; hashes prevent original-envelope replay. No undo, no deletion of inbox/chat/receipt logs. Ordering is original admission, not wall-clock age.')

    def archive_candidate(self, limit=1000):
        """Freeze exact prospective segment bytes/manifest; no filesystem side effects."""
        if type(limit) is not int or not 1 <= limit <= ARCHIVE_SEGMENT_MAX_RECORDS:
            raise ValueError('Archive preview limit is 1..10000 compacted identities.')
        with self.lock:
            if self.lease is None:
                raise RuntimeError('Recovery store is closed.')
            if self.schema == SCHEMA and self.tombstones:
                raise ValueError('Legacy recovery schema cannot contain compacted identities.')
            document = dict(schema_version=self.schema, rows=self.rows)
            if self.schema == COMPACT_SCHEMA:
                document['tombstones'] = self.tombstones
            self.validate(document)
            selected = {key:copy.deepcopy(self.tombstones[key]) for key in sorted(self.tombstones)[:limit]}
            payload = dict(schema_version=ARCHIVE_SEGMENT_SCHEMA, records=selected)
            encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(',',':'), allow_nan=False).encode('utf-8') if selected else b''
            digest = hashlib.sha256(encoded).hexdigest() if selected else None
            source_version = hashlib.sha256(json.dumps([self.epoch, document, limit,
                self.max_rows, self.max_tombstones, MAX_BYTES,
                ARCHIVE_SEGMENT_MAX_BYTES, ARCHIVE_SEGMENT_MAX_RECORDS], sort_keys=True, ensure_ascii=True).encode()).hexdigest()
            fits = bool(selected) and len(encoded)<=ARCHIVE_SEGMENT_MAX_BYTES
            manifest = dict(schema_version=ARCHIVE_PREVIEW_SCHEMA, source_version=source_version,
                source_schema=self.schema, selection_order='identity_hash_ascending', limit=limit,
                selected_count=len(selected), omitted=len(self.tombstones)-len(selected),
                selected_entry_ids=list(selected), segment_schema=ARCHIVE_SEGMENT_SCHEMA,
                segment_sha256=digest, segment_bytes=len(encoded),
                segment_record_limit=ARCHIVE_SEGMENT_MAX_RECORDS, segment_byte_limit=ARCHIVE_SEGMENT_MAX_BYTES,
                proposed_archive_limits=dict(segments=8,total_bytes=32*1024*1024,implemented=False),
                candidate_fits=fits, selection_reason='no_compacted_identities' if not selected else 'within_segment_limits' if fits else 'segment_byte_limit',
                active_index_count=len(self.tombstones), actual_slots_freed=0,
                hypothetical_slots_freed=len(selected) if fits else 0,
                archive_state='not_created', archive_activation_available=False, migration_performed=False,
                privacy='Private identity/content hashes and metadata; not anonymized and no full message text.',
                note='Read-only candidate only. No archive was written or activated, no identity was removed, and duplicate lookup is unchanged. '
                     'A future activation must revalidate source and bytes and preserve lookup through every referenced segment.')
            return encoded, manifest

    def archive_preview(self, limit=1000):
        """Metadata-only command projection; candidate bytes stay out of receipts."""
        return self.archive_candidate(limit)[1]

    def compact(self, keep_terminal, limit, version):
        with self.lock:
            preview = self.compaction_preview(keep_terminal,limit)
            if version != preview['version']:
                raise ValueError('Recovery store changed/reloaded; preview compaction again.')
            rows, tombstones = copy.deepcopy(self.rows), copy.deepcopy(self.tombstones)
            for selected in preview['selected']:
                key = selected['entry_id']
                tombstones[key] = {k:selected[k] for k in ('text_sha256','text_chars','phase','attempt')}
                del rows[key]
            if preview['selected_count']:
                self._publish(rows, tombstones=tombstones)
            return dict(compacted_count=preview['selected_count'], discarded_text_chars=preview['text_chars'],
                        summary=self.summary(), remaining_candidates=preview['remaining_candidates'],
                        selection_reason=preview['selection_reason'], capacity_blocked=preview['capacity_blocked'],
                        note=preview['note'])

    def claim(self, identities):
        with self.lock:
            wanted = {identity_key(i) for i in identities}
            rows, accepted = copy.deepcopy(self.rows), set()
            for row in rows.values():
                key = identity_key(row['identity'])
                if key in wanted and row['phase'] == 'queued':
                    row.update(phase='claimed', revision=row['revision']+1)
                    accepted.add(key)
            if accepted:
                self._publish(rows)
            return accepted

    def delivery(self, references, phase, turn_id, sequence, request_started):
        with self.lock:
            wanted = {identity_key(i) for i in references}
            rows, changed = copy.deepcopy(self.rows), False
            for row in rows.values():
                if identity_key(row['identity']) not in wanted:
                    continue
                if phase == 'preparing' and row['phase'] != 'claimed':
                    raise ValueError('Recovered input was not freshly claimed; explicit retry is required.')
                if row['phase'] not in ACTIVE:
                    continue
                if row['turn_id'] and row['turn_id'] != turn_id or sequence <= row['sequence']:
                    continue
                row.update(phase=phase, turn_id=turn_id, sequence=sequence,
                           request_started=row['request_started'] or request_started, revision=row['revision']+1)
                changed = True
            if changed:
                self._publish(rows)

    def abandon_claims(self, identities):
        with self.lock:
            wanted = {identity_key(i) for i in identities}
            rows = copy.deepcopy(self.rows)
            changed = False
            for row in rows.values():
                if identity_key(row['identity']) in wanted and row['phase'] == 'claimed':
                    row.update(phase='not_sent', revision=row['revision']+1)
                    changed = True
            if changed:
                self._publish(rows)

    def act(self, entry_id, version, *, retry=False, allow_uncertain=False):
        with self.lock:
            row = self.rows.get(entry_id)
            if row is None or self.version(entry_id, row) != version:
                raise ValueError('Recovery entry changed/reloaded; inspect again.')
            if row['phase'] in ACTIVE or row['phase'] == 'responded':
                raise ValueError('Active/responded input cannot be retried or cancelled here; inspect or use Cancel work.')
            if retry and row['phase'] == 'queued':
                raise ValueError('Input is already queued.')
            if retry and (row['request_started'] or row['phase'] == 'uncertain') and not allow_uncertain:
                raise ValueError('Previous delivery is uncertain; inspect before explicitly choosing allow_uncertain.')
            rows = copy.deepcopy(self.rows)
            changed = rows[entry_id]
            changed['revision'] += 1
            if retry:
                identity = dict(client_id=row['identity']['client_id'], request_id='retry-'+uuid.uuid4().hex, message_id='retry-'+uuid.uuid4().hex)
                changed.update(identity=identity, phase='queued', attempt=row['attempt']+1, request_started=False, turn_id='', sequence=0)
            else:
                changed['phase'] = 'cancelled'
            self._publish(rows)
            return copy.deepcopy(changed)

    def preview_reconciliation(self, entry_id, version, receipt_path):
        from aurora_recovery_reconciliation import delivery_evidence
        with self.lock:
            row=self.rows.get(entry_id)
            if row is None or self.version(entry_id,row)!=version:
                raise ValueError('Recovery entry changed/reloaded; inspect again.')
            evidence=delivery_evidence(receipt_path,row)
            return dict(entry_id=entry_id,version=version,evidence_version=evidence['version'],
                before=dict(phase=row['phase'],sequence=row['sequence'],request_started=row['request_started'],attempt=row['attempt']),
                after=evidence['terminal'],turn_id=row['turn_id'],identity=copy.deepcopy(row['identity']),
                evidence=evidence['evidence'],coverage=evidence['coverage'],
                apply_command=f"RECONCILE_INPUT_DELIVERY({entry_id},{version},{evidence['version']})",
                note='Recovery bookkeeping only. Does not restore reply text/context, resend input, execute actions or verify remote cancellation.')

    def reconcile_delivery(self, entry_id, version, evidence_version, receipt_path, *, before_publish=None):
        with self.lock:
            preview=self.preview_reconciliation(entry_id,version,receipt_path)
            if preview['evidence_version']!=evidence_version:
                raise ValueError('Delivery evidence changed; preview reconciliation again.')
            rows=copy.deepcopy(self.rows);row=rows[entry_id]
            row.update(preview['after'],revision=row['revision']+1)
            if before_publish is not None:before_publish()
            self._publish(rows)
            return dict(entry_id=entry_id,before=preview['before'],after=preview['after'],
                        evidence=preview['evidence'],evidence_version=evidence_version,
                        version=self.version(entry_id,row),note=preview['note'])
