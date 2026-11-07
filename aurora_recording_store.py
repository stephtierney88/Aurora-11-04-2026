"""Transactional bounded recording store; metadata only, never action replay."""
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import time

from aurora_execution_history import ordinary, canonical
from aurora_execution_projection import normalize_inspection
from aurora_execution_recording import KINDS, MAX_RECORD_BYTES
from aurora_recording_gate import RecordingGate

MAX_SESSIONS = 32
MAX_RECORDS = 4096
MAX_SESSION_RECORDS = 1024
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_DB_BYTES = 128 * 1024 * 1024
MAX_BATCH = 4
MAX_REQUEST_BYTES = 4 * MAX_RECORD_BYTES + 16384
MAX_PAGE_RECORDS = 32
MAX_PAGE_BYTES = 8 * MAX_RECORD_BYTES
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
SESSION = re.compile(r'[0-9a-f]{32}\Z')
IDENTITY = re.compile(r'[A-Za-z0-9_.:-]{1,160}\Z')
GAP_REASONS = {'capacity','invalid_boundary','invalid_identity','unavailable_projection',
               'invalid_time','record_bytes','buffer_bytes','projection_error'}


class RecordingStoreError(ValueError):
    pass


def integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= 1000000000:
        raise RecordingStoreError('invalid_counter')
    return value


def session_id(value):
    if not isinstance(value,str) or not SESSION.fullmatch(value):
        raise RecordingStoreError('invalid_session')
    return value


def gaps(value, frontier, total):
    if not isinstance(value,list) or len(value)>16:
        raise RecordingStoreError('invalid_gaps')
    previous,count=0,0
    for row in value:
        if not isinstance(row,dict) or set(row)!={'first','last','reason'}:
            raise RecordingStoreError('invalid_gaps')
        first,last=integer(row['first'],1),integer(row['last'],1)
        if not previous < first <= last <= frontier or row['reason'] not in GAP_REASONS:
            raise RecordingStoreError('invalid_gaps')
        previous=last;count+=last-first+1
    if count>total:raise RecordingStoreError('invalid_gaps')
    return value


def normalize_manifest(value):
    if not isinstance(value,dict):raise RecordingStoreError('invalid_manifest')
    result={'session_id':session_id(value.get('session_id'))}
    for key in ('sequence','accepted','dropped','gap_ranges_omitted','after_close_ignored'):
        result[key]=integer(value.get(key))
    if value.get('state') not in ('buffering','closed') or result['accepted']+result['dropped']!=result['sequence']:
        raise RecordingStoreError('invalid_manifest')
    result['state']=value['state']
    result['gaps']=gaps(value.get('gaps'),result['sequence'],result['dropped'])
    return result


def normalize_record(value):
    if not isinstance(value,dict) or value.get('schema')!='aurora_execution_boundary_v1':
        raise RecordingStoreError('unsupported_record')
    keys={'schema','session_id','sequence','kind','identity','observed_at_epoch','source','task_id',
          'task_event_sequence','inspection','gaps_before','gap_ranges_omitted','dropped_total_before'}
    if set(value)!=keys:raise RecordingStoreError('invalid_record')
    result=dict(value)
    result['session_id']=session_id(value['session_id'])
    for key in ('sequence','task_event_sequence','gap_ranges_omitted','dropped_total_before'):
        result[key]=integer(value[key],1 if key=='sequence' else 0)
    if value['kind'] not in KINDS or value['source']!='controller_boundary':raise RecordingStoreError('invalid_record')
    for key in ('identity','task_id'):
        if not isinstance(value[key],str) or not IDENTITY.fullmatch(value[key]):raise RecordingStoreError('invalid_identity')
    epoch=value['observed_at_epoch']
    if type(epoch) not in (int,float) or not math.isfinite(epoch) or epoch<=0:raise RecordingStoreError('invalid_time')
    clean=normalize_inspection(value['inspection']);clean.pop('notice',None)
    original={k:v for k,v in value['inspection'].items() if k!='notice'}
    if clean!=original or clean['task']['task_id']!=value['task_id']:raise RecordingStoreError('invalid_projection')
    result['inspection']=clean
    result['gaps_before']=gaps(value['gaps_before'],value['sequence']-1,result['dropped_total_before'])
    data=canonical(result)
    if len(data)>MAX_RECORD_BYTES:raise RecordingStoreError('record_too_large')
    return result,data,hashlib.sha256(data).hexdigest()


def unavailable_ranges(manifest, sequences):
    """Bounded interval arithmetic; unknown holes are never called known drops."""
    missing = []
    cursor = 1
    for sequence in [*sequences, manifest['sequence'] + 1]:
        if cursor < sequence:
            end = sequence - 1
            for gap in manifest['gaps']:
                first, last = max(cursor, gap['first']), min(end, gap['last'])
                if first <= last:
                    if cursor < first:
                        missing.append(dict(first=cursor, last=first-1, status='unavailable_unknown'))
                    missing.append(dict(first=first, last=last, status='recorded_drop', reason=gap['reason']))
                    cursor = last + 1
            if cursor <= end:
                missing.append(dict(first=cursor, last=end, status='unavailable_unknown'))
        cursor = sequence + 1
    return dict(ranges=missing[:64], omitted_ranges=max(0, len(missing)-64),
                unavailable_total=manifest['sequence']-len(sequences),
                uncommitted_accepted=max(0, manifest['accepted']-len(sequences)))


def decode_stored_record(identity, sequence, row, expected_digest=None):
    """Validate the selected bytes before returning any inspection content."""
    if not row:
        raise RecordingStoreError('missing')
    digest, length, payload = row
    if expected_digest is not None:
        if not isinstance(expected_digest, str) or not DIGEST.fullmatch(expected_digest):
            raise RecordingStoreError('invalid_digest')
        if digest != expected_digest:
            raise RecordingStoreError('record_changed')
    if not isinstance(digest, str) or not DIGEST.fullmatch(digest) or not isinstance(payload, bytes):
        raise RecordingStoreError('corrupt')
    if length != len(payload) or length > MAX_RECORD_BYTES or hashlib.sha256(payload).hexdigest() != digest:
        raise RecordingStoreError('corrupt')
    value, normalized, _ = normalize_record(json.loads(payload))
    if payload != normalized or value['session_id'] != identity or value['sequence'] != sequence:
        raise RecordingStoreError('corrupt')
    return value, digest


class RecordingStore:
    def __init__(self,root):
        self.root=Path(root).absolute()
        self.path=self.root/'history.sqlite3'

    @contextmanager
    def connection(self,write=False):
        if write:self.root.mkdir(parents=True,exist_ok=True)
        ordinary(self.root,directory=True)
        existed=self.path.exists()
        for suffix in ('','-journal','-wal','-shm'):
            target=Path(str(self.path)+suffix)
            if target.exists() or target.is_symlink():
                if ordinary(target).st_size>MAX_DB_BYTES:raise RecordingStoreError('database_too_large')
        if not existed and not write:raise RecordingStoreError('missing')
        con=sqlite3.connect(str(self.path) if write else self.path.as_uri()+'?mode=ro',uri=not write,timeout=.25)
        try:
            if write:
                con.execute('PRAGMA journal_mode=DELETE')
                con.execute('PRAGMA synchronous=FULL')
                page=con.execute('PRAGMA page_size').fetchone()[0]
                con.execute('PRAGMA max_page_count='+str(MAX_DB_BYTES//page))
                con.execute('BEGIN IMMEDIATE')
            else:
                # Manifest/index/page must share one read snapshot while a writer appends.
                con.execute('BEGIN')
            version=con.execute('PRAGMA user_version').fetchone()[0]
            # A crash can leave an empty SQLite file before schema publication.
            # Re-initialize only an actually empty schema, never unknown tables.
            empty_schema = not con.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
            if version==0 and empty_schema and write:
                con.execute('CREATE TABLE sessions (id TEXT PRIMARY KEY, manifest TEXT NOT NULL, updated REAL NOT NULL)')
                con.execute('CREATE TABLE records (session TEXT NOT NULL, sequence INTEGER NOT NULL, digest TEXT NOT NULL, payload BLOB NOT NULL, PRIMARY KEY(session,sequence))')
                con.execute('PRAGMA user_version=1')
                con.commit()
                con.execute('BEGIN IMMEDIATE')
            elif version not in (1,2):raise RecordingStoreError('unsupported_store')
            yield con
            if write:con.commit()
        finally:
            con.close()

    def publish(self,manifest,records):
        manifest=normalize_manifest(manifest);identity=manifest['session_id']
        if not isinstance(records,list) or len(records)>MAX_BATCH:raise RecordingStoreError('invalid_batch')
        rows=[normalize_record(record) for record in records]
        sequences=[row[0]['sequence'] for row in rows]
        if sequences!=sorted(set(sequences)):raise RecordingStoreError('invalid_batch')
        for record,_,_ in rows:
            if record['session_id']!=identity or record['sequence']>manifest['sequence'] or record['dropped_total_before']>manifest['dropped']:
                raise RecordingStoreError('manifest_conflict')
            if any(g['first']<=record['sequence']<=g['last'] for g in manifest['gaps']):raise RecordingStoreError('manifest_conflict')
        with RecordingGate(self.root), self.connection(write=True) as con:
            if con.execute('PRAGMA user_version').fetchone()[0]==2 and con.execute(
                    'SELECT 1 FROM retired_sessions WHERE id=?',(identity,)).fetchone():
                raise RecordingStoreError('session_retired')
            old=con.execute('SELECT manifest FROM sessions WHERE id=?',(identity,)).fetchone()
            if old:
                old=json.loads(old[0])
                if any(manifest[k]<old[k] for k in ('sequence','accepted','dropped','gap_ranges_omitted','after_close_ignored')):
                    raise RecordingStoreError('manifest_regression')
                if old['state']=='closed' and manifest!=old:raise RecordingStoreError('session_closed')
            elif con.execute('SELECT count(*) FROM sessions').fetchone()[0]>=MAX_SESSIONS:
                raise RecordingStoreError('session_capacity')
            last=con.execute('SELECT coalesce(max(sequence),0) FROM records WHERE session=?',(identity,)).fetchone()[0]
            for record,data,digest in rows:
                prior=con.execute('SELECT digest,length(payload),substr(payload,1,?) FROM records WHERE session=? AND sequence=?',
                                  (MAX_RECORD_BYTES+1,identity,record['sequence'])).fetchone()
                if prior:
                    if prior[0]!=digest or prior[1]!=len(data) or bytes(prior[2])!=data:raise RecordingStoreError('record_conflict')
                else:
                    if record['sequence']<=last or old and old['state']=='closed':raise RecordingStoreError('sequence_conflict')
                    con.execute('INSERT INTO records VALUES(?,?,?,?)',(identity,record['sequence'],digest,data))
                    last=record['sequence']
            count=con.execute('SELECT count(*) FROM records WHERE session=?',(identity,)).fetchone()[0]
            total,size=con.execute('SELECT count(*),coalesce(sum(length(payload)),0) FROM records').fetchone()
            if count>MAX_SESSION_RECORDS or total>MAX_RECORDS or size>MAX_PAYLOAD_BYTES:raise RecordingStoreError('record_capacity')
            if count>manifest['accepted'] or manifest['state']=='closed' and count!=manifest['accepted']:
                raise RecordingStoreError('incomplete_close')
            con.execute('INSERT INTO sessions VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET manifest=excluded.manifest,updated=excluded.updated',
                        (identity,canonical(manifest).decode(),time.time()))
        return dict(status='committed',session_id=identity,sequences=sequences,
                    digests=[row[2] for row in rows],closed=manifest['state']=='closed')

    def sessions(self):
        if not self.path.exists():return dict(status='listed',sessions=[])
        with self.connection() as con:
            rows=con.execute('SELECT substr(id,1,33),updated FROM sessions ORDER BY updated DESC LIMIT ?', (MAX_SESSIONS+1,)).fetchall()
            if len(rows)>MAX_SESSIONS:raise RecordingStoreError('session_capacity')
            result=[]
            for identity,updated in rows:
                try:
                    state, _ = self._session_state(con, identity)
                    observed = updated if type(updated) in (int,float) and math.isfinite(updated) and updated>0 else None
                    result.append(dict(state, status='available', updated_at_epoch=observed))
                except (ValueError, TypeError, KeyError) as error:
                    safe_id = identity if isinstance(identity,str) and SESSION.fullmatch(identity) else None
                    reason = str(error) if isinstance(error,RecordingStoreError) else 'unreadable_manifest'
                    result.append(dict(session_id=safe_id,status='invalid_session_metadata',reason=reason,closure='unknown'))
        return dict(status='listed',sessions=result,capacity=MAX_SESSIONS,
                    ordering='Most recently published first; not causal order across sessions.')

    def _session_state(self, con, identity):
        identity = session_id(identity)
        raw = con.execute('SELECT length(manifest),substr(manifest,1,16385) FROM sessions WHERE id=?', (identity,)).fetchone()
        if not raw:
            raise RecordingStoreError('missing_session')
        if raw[0] > 16384:
            raise RecordingStoreError('invalid_manifest')
        manifest = normalize_manifest(json.loads(raw[1]))
        index = con.execute('SELECT sequence,substr(digest,1,65),length(payload) FROM records WHERE session=? ORDER BY sequence LIMIT ?',
                            (identity,MAX_SESSION_RECORDS+1)).fetchall()
        if len(index) > MAX_SESSION_RECORDS:
            raise RecordingStoreError('record_capacity')
        sequences = [integer(row[0],1) for row in index]
        if manifest['session_id'] != identity or (sequences and sequences[-1] > manifest['sequence']):
            raise RecordingStoreError('manifest_conflict')
        if len(index)>manifest['accepted'] or manifest['state']=='closed' and len(index)!=manifest['accepted']:
            raise RecordingStoreError('incomplete_manifest')
        if any(gap['first']<=seq<=gap['last'] for gap in manifest['gaps'] for seq in sequences):
            raise RecordingStoreError('manifest_conflict')
        # Index digests are not trusted content until an individual record is checked.
        safe_index = [(seq, digest if isinstance(digest,str) and DIGEST.fullmatch(digest) else 'invalid', length)
                      for seq,digest,length in index]
        version = hashlib.sha256(canonical(dict(manifest=manifest,index=safe_index))).hexdigest()
        return dict(session_id=identity,manifest=manifest,committed_count=len(index),
                    last_committed_sequence=sequences[-1] if sequences else 0,version=version,
                    coverage=unavailable_ranges(manifest,sequences),
                    closure='closed' if manifest['state']=='closed' else 'not_closed; active or interrupted unknown'), index

    def timeline(self, identity, *, after_sequence=0, limit=16, expected_version=None):
        identity=session_id(identity); after_sequence=integer(after_sequence); limit=integer(limit,1)
        if limit>MAX_PAGE_RECORDS:
            raise RecordingStoreError('invalid_page_size')
        with self.connection() as con:
            state,index=self._session_state(con,identity)
            if expected_version is not None and expected_version!=state['version']:
                raise RecordingStoreError('session_changed')
            eligible=[row for row in index if row[0]>after_sequence]
            selected=[]; consumed=0
            for sequence,_,length in eligible[:limit]:
                cost=min(length,MAX_RECORD_BYTES+1)
                if selected and consumed+cost>MAX_PAGE_BYTES:
                    break
                consumed+=cost
                stored=con.execute('SELECT substr(digest,1,65),length(payload),substr(payload,1,?) FROM records WHERE session=? AND sequence=?',
                                   (MAX_RECORD_BYTES+1,identity,sequence)).fetchone()
                selected.append((sequence,stored))
        # Release the read transaction before CPU-heavy projection/checksum work.
        rows=[]
        for sequence,stored in selected:
            try:
                value,digest=decode_stored_record(identity,sequence,stored)
                rows.append(dict(sequence=sequence,status='available',digest=digest,
                                 **{key:value[key] for key in ('kind','identity','task_id','task_event_sequence','observed_at_epoch')}))
            except (ValueError,TypeError,KeyError):
                rows.append(dict(sequence=sequence,status='corrupt_or_unsupported'))
        return dict(status='timeline',**state,records=rows,after_sequence=after_sequence,
                    next_after=rows[-1]['sequence'] if rows and len(eligible)>len(rows) else None,
                    order='Sequence within this session only; event timestamps may move backwards.',
                    integrity='Listed available records checked; checksum is not a signature.')

    def record(self,identity,sequence,expected_digest=None):
        identity=session_id(identity);sequence=integer(sequence,1)
        with self.connection() as con:
            row=con.execute('SELECT substr(digest,1,65),length(payload),substr(payload,1,?) FROM records WHERE session=? AND sequence=?',
                            (MAX_RECORD_BYTES+1,identity,sequence)).fetchone()
        value,digest=decode_stored_record(identity,sequence,row,expected_digest)
        return dict(status='loaded',record=value,digest=digest,integrity='checksum_not_signature')


def store_action(root,request):
    try:
        store=RecordingStore(root)
        if request.get('operation')=='publish':return store.publish(request.get('manifest'),request.get('records'))
        if request.get('operation')=='list':return store.sessions()
        if request.get('operation')=='timeline':return store.timeline(request.get('session_id'),after_sequence=request.get('after_sequence',0),limit=request.get('limit',16),expected_version=request.get('expected_version'))
        if request.get('operation')=='record':return store.record(request.get('session_id'),request.get('sequence'),request.get('expected_digest'))
        if request.get('operation') in ('preview_remove','remove','removal_status'):
            from aurora_recording_retention import retention_action
            return retention_action(store,request)
        raise RecordingStoreError('invalid_operation')
    except (RecordingStoreError,FileNotFoundError) as error:
        return dict(status=str(error) if isinstance(error,RecordingStoreError) else 'missing')
    except (sqlite3.Error,OSError):
        status={'publish':'publication_uncertain','remove':'removal_uncertain'}.get(request.get('operation'),'unreadable')
        return dict(status=status,session_ids=request.get('session_ids',[]) if status=='removal_uncertain' else [])
    except (ValueError,TypeError,KeyError):return dict(status='invalid_record')


def main():
    if len(sys.argv)==3 and sys.argv[1]=='--worker':
        raw=sys.stdin.buffer.read(MAX_REQUEST_BYTES+1)
        try:
            if len(raw)>MAX_REQUEST_BYTES:raise ValueError()
            request=json.loads(raw)
            if not isinstance(request,dict):raise ValueError()
            result=store_action(sys.argv[2],request)
        except ValueError:result=dict(status='invalid_request')
    else:
        import argparse
        parser=argparse.ArgumentParser(description='Read recording metadata; no replay or runtime restore.')
        parser.add_argument('operation',choices=('list','record','timeline','preview_remove','remove','removal_status'))
        parser.add_argument('session_id',nargs='?');parser.add_argument('sequence',nargs='?',type=int)
        parser.add_argument('--after-sequence',type=int,default=0);parser.add_argument('--limit',type=int,default=16)
        parser.add_argument('--expected-version');parser.add_argument('--expected-digest')
        parser.add_argument('--session-ids',nargs='+');parser.add_argument('--confirm',action='store_true')
        parser.add_argument('--include-incomplete',action='store_true')
        args=parser.parse_args()
        retention=args.operation in ('preview_remove','remove','removal_status')
        if retention and (args.session_id is not None or args.sequence is not None or args.expected_digest is not None):
            parser.error('retention uses --session-ids, not positional record selectors')
        if not retention and (args.session_ids is not None or args.confirm or args.include_incomplete):
            parser.error('retention flags require a retention operation')
        if args.confirm and args.operation!='remove':parser.error('--confirm requires remove')
        if args.include_incomplete and args.operation not in ('preview_remove','remove'):
            parser.error('--include-incomplete requires preview_remove or remove')
        if args.operation=='timeline' and (args.sequence is not None or args.expected_digest is not None):
            parser.error('timeline uses --after-sequence / --expected-version; no positional sequence or --expected-digest')
        if args.operation!='timeline' and (args.after_sequence!=0 or args.limit!=16 or args.expected_version is not None and args.operation!='remove'):
            parser.error('--after-sequence / --limit / --expected-version require timeline')
        if args.operation!='record' and args.expected_digest is not None:
            parser.error('--expected-digest requires record')
        result=store_action(Path(__file__).resolve().parent/'execution_recordings',vars(args))
    print(json.dumps(result,ensure_ascii=True,separators=(',',':')))


if __name__=='__main__':
    # Retention imports the store's validators/errors. Keep one module identity in workers.
    sys.modules.setdefault('aurora_recording_store',sys.modules[__name__])
    main()
