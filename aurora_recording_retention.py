"""Explicit, version-checked recording retention; never automatic eviction."""
import hashlib
import json
import time

from aurora_execution_history import canonical
from aurora_recording_gate import RecordingGate
from aurora_recording_store import (RecordingStoreError, session_id, decode_stored_record,
    MAX_SESSIONS, MAX_RECORDS, MAX_PAYLOAD_BYTES, MAX_RECORD_BYTES, DIGEST)

MAX_SELECTION = 16
MAX_RETIRED = 2048


def selected_ids(value):
    if not isinstance(value,list) or not 1 <= len(value) <= MAX_SELECTION:
        raise RecordingStoreError('invalid_selection')
    ids = sorted(session_id(item) for item in value)
    if len(set(ids)) != len(ids):
        raise RecordingStoreError('invalid_selection')
    return ids


def archive_preview(store, con, ids, include_incomplete):
    """Hash a bounded coherent archive, validating every selected record before removal."""
    count, size = con.execute('SELECT count(*),coalesce(sum(length(payload)),0) FROM records').fetchone()
    if count > MAX_RECORDS or size > MAX_PAYLOAD_BYTES:
        raise RecordingStoreError('record_capacity')
    manifests = con.execute('SELECT id,length(manifest),substr(manifest,1,16385),updated FROM sessions ORDER BY id LIMIT ?',
                            (MAX_SESSIONS+1,)).fetchall()
    if len(manifests)>MAX_SESSIONS or any(row[1]>16384 for row in manifests):
        raise RecordingStoreError('invalid_archive')
    schema = con.execute('PRAGMA user_version').fetchone()[0]
    retired = con.execute('SELECT id,retired_at,evidence_hash FROM retired_sessions ORDER BY id LIMIT ?',
                          (MAX_RETIRED+1,)).fetchall() if schema==2 else []
    if len(retired)+len(ids)>MAX_RETIRED:
        raise RecordingStoreError('retirement_capacity')
    digest=hashlib.sha256(canonical(dict(schema=schema,manifests=manifests,retired=retired,
                                        selected=ids,include_incomplete=include_incomplete)))
    selected={}
    for identity in ids:
        state,_=store._session_state(con,identity)
        if state['manifest']['state']!='closed' and not include_incomplete:
            raise RecordingStoreError('incomplete_protected')
        selected[identity]=dict(state,payload_bytes=0)
    for identity,sequence,record_digest,length,data in con.execute(
            'SELECT session,sequence,digest,length(payload),substr(payload,1,?) FROM records ORDER BY session,sequence',
            (MAX_RECORD_BYTES+1,)):
        if not isinstance(data,bytes) or len(data)!=length or length>MAX_RECORD_BYTES:
            raise RecordingStoreError('invalid_archive')
        digest.update(canonical([identity,sequence,record_digest,length,hashlib.sha256(data).hexdigest()]))
        if identity in selected:
            decode_stored_record(identity,sequence,(record_digest,length,data))
            selected[identity]['payload_bytes']+=length
    rows=[selected[identity] for identity in ids]
    return dict(status='removal_preview',session_ids=ids,version=digest.hexdigest(),sessions=rows,
                include_incomplete=include_incomplete,record_count=sum(row['committed_count'] for row in rows),
                payload_bytes=sum(row['payload_bytes'] for row in rows),
                archive_usage=dict(sessions=len(manifests),session_capacity=MAX_SESSIONS,records=count,
                    record_capacity=MAX_RECORDS,payload_bytes=size,payload_capacity=MAX_PAYLOAD_BYTES,
                    retired_ids=len(retired),retired_capacity=MAX_RETIRED),
                effect='Permanently remove only these stored sessions; retain retired IDs to reject delayed writers. '
                       'Incomplete recordings may have an unknown unwritten suffix. Loaded inspector view, manual snapshots '
                       'and screenshots are unchanged. Logical capacity is freed; database file size may not shrink. '
                       'First removal upgrades this archive to v2; older v1-only Aurora builds cannot read it.')


def removal_status(store, ids):
    """Resolve lost acknowledgement by reading persistent evidence, never replaying deletion."""
    with store.connection() as con:
        schema=con.execute('PRAGMA user_version').fetchone()[0]
        rows=[]
        for identity in ids:
            present=con.execute('SELECT 1 FROM sessions WHERE id=?',(identity,)).fetchone()
            retired=con.execute('SELECT retired_at,evidence_hash FROM retired_sessions WHERE id=?',(identity,)).fetchone() if schema==2 else None
            rows.append(dict(session_id=identity,status='conflict' if present and retired else
                             'present' if present else 'retired' if retired else 'missing_unknown',
                             retired_at_epoch=retired[0] if retired else None,
                             evidence_hash=retired[1] if retired else None))
    return dict(status='removal_status',sessions=rows,session_ids=ids)


def retention_action(store, request):
    ids=selected_ids(request.get('session_ids'))
    operation=request['operation']
    if operation=='removal_status':return removal_status(store,ids)
    include=request.get('include_incomplete',False)
    if type(include) is not bool:raise RecordingStoreError('invalid_option')
    if operation=='remove':
        if request.get('confirm') is not True:raise RecordingStoreError('confirmation_required')
        version=request.get('expected_version')
        if not isinstance(version,str) or not DIGEST.fullmatch(version):raise RecordingStoreError('invalid_version')
    if not store.path.exists():raise RecordingStoreError('missing')
    try:gate=RecordingGate(store.root,exclusive=True)
    except OSError as error:
        winerror=getattr(error,'winerror',None)
        if winerror in (32,33) or winerror is None and error.errno in (11,13):
            raise RecordingStoreError('recording_active_or_retention_busy') from None
        raise
    with gate, store.connection(write=operation=='remove') as con:
        preview=archive_preview(store,con,ids,include)
        if operation=='preview_remove':return preview
        if preview['version']!=version:raise RecordingStoreError('archive_changed')
        if con.execute('PRAGMA user_version').fetchone()[0]==1:
            # Opt-in migration: older readers must reject v2 rather than resurrect a retired ID.
            con.execute('CREATE TABLE retired_sessions (id TEXT PRIMARY KEY, retired_at REAL NOT NULL, evidence_hash TEXT NOT NULL)')
            con.execute('PRAGMA user_version=2')
        retired_at=time.time()
        for identity in ids:
            con.execute('INSERT INTO retired_sessions VALUES(?,?,?)',(identity,retired_at,version))
            con.execute('DELETE FROM records WHERE session=?',(identity,))
            con.execute('DELETE FROM sessions WHERE id=?',(identity,))
    return dict(status='removed',session_ids=ids,version=version,retired_at_epoch=retired_at,
                record_count=preview['record_count'],payload_bytes=preview['payload_bytes'],
                effect=preview['effect'])
