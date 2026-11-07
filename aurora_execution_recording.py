"""Opt-in in-memory boundary feed. No disk, worker, runtime action or replay.

The owning TaskContinuation lock serializes offers, inspection and prefix acks.
An acknowledgement is a consumer claim, not evidence of durable storage.
"""
from collections import deque
import copy
import json
import math
import re
import time
import uuid


KINDS = frozenset({'task_started', 'turn_reserved', 'request_prepared',
                   'request_finalized', 'command_receipt', 'frame_observed', 'task_stopped'})
MAX_RECORD_BYTES = 1024 * 1024
MAX_BUFFER_BYTES = 4 * MAX_RECORD_BYTES
MAX_CAPACITY = 16
MAX_GAPS = 16


class BoundaryBuffer:
    """One session/sequence owner; preserve queued records and drop newest on pressure."""
    def __init__(self, capacity, *, epoch_clock=time.time):
        if type(capacity) is not int or not 1 <= capacity <= MAX_CAPACITY:
            raise ValueError('Recording capacity must be 1..16.')
        self.capacity, self.epoch_clock = capacity, epoch_clock
        self.session_id = uuid.uuid4().hex
        self.records = deque()
        self.buffer_bytes = self.sequence = self.accepted = self.acknowledged = 0
        self.dropped = self.gaps_omitted = self.after_close = 0
        self.gaps = []
        self.closed = False

    def _drop(self, reason):
        self.dropped += 1
        if self.gaps and self.gaps[-1]['last'] == self.sequence-1 and self.gaps[-1]['reason'] == reason:
            self.gaps[-1]['last'] = self.sequence
        else:
            self.gaps.append(dict(first=self.sequence, last=self.sequence, reason=reason))
            if len(self.gaps) > MAX_GAPS:
                self.gaps.pop(0)
                self.gaps_omitted += 1
        return False

    def offer(self, kind, snapshot_factory, *, identity):
        """Freeze one completed controller boundary; never block for a consumer."""
        if self.closed:
            self.after_close += 1
            return False
        self.sequence += 1
        if len(self.records) >= self.capacity:
            return self._drop('capacity')
        try:
            if kind not in KINDS:
                return self._drop('invalid_boundary')
            if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', identity):
                return self._drop('invalid_identity')
            from aurora_execution_projection import inspection_snapshot
            task = snapshot_factory()
            inspection = inspection_snapshot({'continuation': {'mode': 'bounded', 'active_task': task}})
            if not inspection['available']:
                return self._drop('unavailable_projection')
            epoch = self.epoch_clock()
            if type(epoch) not in (int, float) or not math.isfinite(epoch) or epoch <= 0:
                return self._drop('invalid_time')
            value = dict(schema='aurora_execution_boundary_v1', session_id=self.session_id,
                sequence=self.sequence, kind=kind, identity=identity, observed_at_epoch=epoch,
                source='controller_boundary', task_id=inspection['task']['task_id'],
                task_event_sequence=inspection['retention'].get('events_total'), inspection=inspection,
                gaps_before=copy.deepcopy(self.gaps), gap_ranges_omitted=self.gaps_omitted,
                dropped_total_before=self.dropped)
            raw = json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False, separators=(',', ':')).encode('utf-8')
            if len(raw) > MAX_RECORD_BYTES:
                return self._drop('record_bytes')
            if self.buffer_bytes + len(raw) > MAX_BUFFER_BYTES:
                return self._drop('buffer_bytes')
        except Exception:
            # Diagnostics must not alter execution or retain arbitrary exception text.
            return self._drop('projection_error')
        self.records.append((self.sequence, raw))
        self.buffer_bytes += len(raw)
        self.accepted += 1
        return True

    def status(self):
        return dict(schema='aurora_execution_recording_v1', enabled=True, session_id=self.session_id,
            state='closed' if self.closed else 'buffering', capacity=self.capacity,
            queued=len(self.records), buffered_bytes=self.buffer_bytes, sequence=self.sequence,
            accepted=self.accepted, acknowledged=self.acknowledged, dropped=self.dropped,
            gaps=copy.deepcopy(self.gaps), gap_ranges_omitted=self.gaps_omitted,
            after_close_ignored=self.after_close, durable=False,
            scope='In-memory controller boundaries only; a consumer acknowledgement does not prove disk persistence.')

    def peek(self, limit=8):
        if type(limit) is not int or not 1 <= limit <= MAX_CAPACITY:
            raise ValueError('Peek limit must be 1..16.')
        return dict(status=self.status(), records=[json.loads(raw) for _, raw in list(self.records)[:limit]])

    def acknowledge(self, session_id, sequences):
        if (session_id != self.session_id or not isinstance(sequences, list) or
                not 1 <= len(sequences) <= MAX_CAPACITY or any(type(n) is not int for n in sequences) or
                sequences != [n for n, _ in list(self.records)[:len(sequences)]]):
            return dict(status='ack_conflict', acknowledged=[])
        for _ in sequences:
            _, raw = self.records.popleft()
            self.buffer_bytes -= len(raw)
        self.acknowledged += len(sequences)
        return dict(status='acknowledged', acknowledged=list(sequences))

    def close(self):
        """Stop accepting; retained records and gap status remain inspectable/drainable."""
        self.closed = True
        return self.status()
