"""One runtime-owned recording writer. Tick never waits for disk publication."""
import copy
import threading
import time

from aurora_execution_history_job import HistoryJob
from aurora_recording_store import MAX_REQUEST_BYTES, MAX_BATCH, normalize_record
from aurora_recording_gate import RecordingGate


class RecordingJob(HistoryJob):
    WORKER_NAME = 'aurora_recording_store.py'
    REQUEST_LIMIT = MAX_REQUEST_BYTES

    def cancel(self, reason='cancelled'):
        result=super().cancel(reason)
        if self.request.get('operation')=='publish':
            result.update(status='publication_uncertain',session_id=self.request['manifest']['session_id'],
                          sequences=[row['sequence'] for row in self.request['records']])
        elif self.request.get('operation')=='remove':
            result.update(status='removal_uncertain',session_ids=self.request.get('session_ids',[]))
        self.result=result
        return copy.deepcopy(result)


class RecordingService:
    def __init__(self,controller,root,*,job_factory=RecordingJob):
        self.controller,self.root,self.job_factory=controller,root,job_factory
        self.lock=threading.RLock()
        self.mode='off';self.state='off';self.job=None;self.pending=None;self.error=''
        self.committed=0;self.last_sequence=0;self.last_receipt={};self.last_manifest=None
        self.gate=None;self.disposed=False

    def set_mode(self,mode):
        if mode not in ('off','boundaries'):raise ValueError('Unknown recording mode.')
        with self.lock:
            if self.disposed:raise ValueError('Recording service is closed.')
            if mode==self.mode:return self.snapshot()
            if mode=='boundaries':
                if self.state not in ('off','closed'):raise ValueError('Previous recording is not closed; inspect/retry it first.')
                try:self.gate=RecordingGate(self.root)
                except OSError:
                    self.error='retention_busy';raise ValueError('Recording store unavailable or retention active.') from None
                try:self.controller.start_recording()
                except Exception:
                    self.gate.close();self.gate=None;raise
                self.committed=self.last_sequence=0;self.last_manifest=None;self.error='';self.state='recording'
            else:
                self.controller.close_recording()
                if self.state!='error':self.state='draining'
            self.mode=mode
            return self.snapshot()

    def retry(self):
        with self.lock:
            if self.disposed:raise ValueError('Recording service is closed.')
            if self.job is not None:raise ValueError('Recording publication is still running.')
            if self.state!='error':return self.snapshot()
            self.error='';self.state='recording' if self.mode=='boundaries' else 'draining'
            # Retain the exact uncertain request until confirmed; no guessed cursor.
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            return dict(mode=self.mode,state=self.state,source='runtime_session',error=self.error,
                committed_records=self.committed,last_committed_sequence=self.last_sequence,
                writer_pid=self.job.process.pid if self.job and self.job.process else None,
                writer_started_at_epoch=self.job.started_at_epoch if self.job else None,
                last_receipt=copy.deepcopy(self.last_receipt),feed=self.controller.recording_status(),
                retention_protected=self.gate is not None,disposed=self.disposed,
                scope='Metadata recordings only. Off may still drain; errors need explicit retry. No automatic deletion or replay.')

    def tick(self):
        """Diagnostic failure must not escape into the task/input scheduler."""
        with self.lock:
            try:
                self._tick_locked()
            except Exception:
                self.error='writer_error';self.state='error'
                if self.job:
                    try:
                        self.last_receipt=self.job.cancel('writer_error')
                        if self.last_receipt.get('owned_resources_closed') is not False:self.job=None
                    except Exception:
                        self.last_receipt=dict(status='cleanup_incomplete',owned_resources_closed=False)

    def _tick_locked(self):
        with self.lock:
            if self.disposed or self.state in ('off','closed','error'):return
            if self.job:
                result=self.job.poll()
                if result is None:return
                self.last_receipt=copy.deepcopy(result)
                if result.get('owned_resources_closed') is False:
                    self.error='cleanup_incomplete';self.state='error';return
                self.job=None
                request=self.pending
                sequences=[row['sequence'] for row in request['records']]
                digests=[normalize_record(row)[2] for row in request['records']]
                if (result.get('status')!='committed' or result.get('session_id')!=request['manifest']['session_id'] or
                    result.get('sequences')!=sequences or result.get('digests')!=digests or result.get('owned_resources_closed') is False):
                    self.error=result.get('status','invalid_receipt') if result.get('status')!='committed' else 'invalid_commit_receipt'
                    self.state='error';return
                if sequences:
                    ack=self.controller.acknowledge_recording(result['session_id'],sequences)
                    if ack['status']!='acknowledged':self.error='ack_conflict';self.state='error';return
                    self.committed+=len(sequences);self.last_sequence=sequences[-1]
                self.last_manifest=request['manifest'];self.pending=None
                if result.get('closed'):
                    self.state='closed'
                    if self.gate:self.gate.close();self.gate=None
                    return
            if self.pending is None:
                batch=self.controller.peek_recording(limit=MAX_BATCH)
                manifest=batch['status']
                if not manifest.get('enabled'):return
                # Close only when this batch contains all remaining accepted records.
                manifest=copy.deepcopy(manifest)
                if manifest['state']=='closed' and manifest['queued']>len(batch['records']):manifest['state']='buffering'
                if not batch['records'] and self.last_manifest and all(manifest.get(k)==self.last_manifest.get(k)
                    for k in ('sequence','dropped','gap_ranges_omitted','after_close_ignored','state')):return
                self.pending=dict(operation='publish',manifest=manifest,records=batch['records'])
            try:self.job=self.job_factory(self.root,self.pending)
            except Exception:
                self.error='writer_unavailable';self.state='error'

    def shutdown(self,timeout=5):
        self.set_mode('off')
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.tick()
            if self.snapshot()['state'] in ('off','closed','error'):break
            time.sleep(.01)
        with self.lock:
            if self.job:
                try:
                    self.last_receipt=self.job.cancel('shutdown_timeout')
                    if self.last_receipt.get('owned_resources_closed') is not False:
                        self.job=None
                    self.error='publication_uncertain'
                except Exception:
                    self.last_receipt=dict(status='cleanup_incomplete',owned_resources_closed=False)
                    self.error='cleanup_incomplete'
                self.state='error'
            elif self.state not in ('off','closed','error'):
                self.error='incomplete_shutdown';self.state='error'
            return self.snapshot()

    def close(self,timeout=5):
        """Final disposal, unlike recoverable shutdown. Never abandon an owned child."""
        with self.lock:
            if self.disposed:return self.snapshot()
            self.shutdown(timeout=timeout)
            if self.job is None:
                self.disposed=True
                if self.gate:self.gate.close();self.gate=None
            return self.snapshot()
