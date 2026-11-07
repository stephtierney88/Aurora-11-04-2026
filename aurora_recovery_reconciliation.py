"""Bounded exact-attempt delivery evidence; never infer delivery from message text."""
import hashlib
import json
import os
from pathlib import Path

from aurora_delivery_receipts import IDENTITY_FIELDS, TURN_PHASES, TERMINAL_PHASES

MAX_SCAN_BYTES = 8 * 1024 * 1024
MAX_SCAN_RECORDS = 4096
MAX_RECORD_BYTES = 64 * 1024


def unique_fields(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate receipt field.')
        result[key] = value
    return result


def delivery_evidence(path, row):
    """A complete observed chain is required inside the bounded committed tail.

    Digest binds exact matching bytes, offsets and file identity. Unrelated appends
    do not invalidate it; replacement, changed evidence and lost coverage do.
    Local receipts are not cryptographic authentication or remote-action proof.
    """
    if not row.get('turn_id') or row.get('phase') not in {'claimed','preparing','prepared','submitted','uncertain'}:
        raise ValueError('Only unresolved input with a recorded turn ID can be reconciled.')
    with Path(path).open('rb') as source:
        before = os.fstat(source.fileno())
        start = max(0, before.st_size - MAX_SCAN_BYTES)
        source.seek(start)
        data = source.read(before.st_size - start)
        after = os.fstat(source.fileno())
    current = Path(path).stat()
    file_id = f'{before.st_dev}:{before.st_ino}'
    if (len(data) != before.st_size-start or after.st_size < before.st_size
            or (current.st_dev,current.st_ino) != (before.st_dev,before.st_ino)
            or current.st_size < before.st_size):
        raise ValueError('Receipt log changed during inspection; preview again.')
    if not data.endswith(b'\n'):
        raise ValueError('Receipt tail is incomplete or empty; no delivery conclusion.')
    if start:
        boundary = data.find(b'\n') + 1
        start += boundary; data = data[boundary:]  # Discard potentially partial leading record.
    lines = data.splitlines(keepends=True)
    if len(lines)>MAX_SCAN_RECORDS:
        skipped=lines[:-MAX_SCAN_RECORDS]
        start += sum(map(len,skipped));lines=lines[-MAX_SCAN_RECORDS:]
    chain=[];offset=start;seen={};terminal=False
    for raw in lines:
        position=offset;offset+=len(raw)
        if len(raw)>MAX_RECORD_BYTES:
            raise ValueError('Receipt window contains an oversized record; evidence is incomplete.')
        if not raw.strip():continue
        try:
            record=json.loads(raw.decode('utf-8-sig' if position==0 else 'utf-8'),object_pairs_hook=unique_fields)
        except (ValueError,UnicodeError):
            raise ValueError('Receipt window contains malformed data; no delivery conclusion.') from None
        if not isinstance(record,dict):raise ValueError('Receipt window contains a non-object record.')
        if (record.get('event')!='message_model_delivery'
                or {key:record.get(key) for key in IDENTITY_FIELDS}!=row['identity']
                or record.get('inference_request_id')!=row['turn_id']):
            continue
        sequence,phase,started=record.get('sequence'),record.get('phase'),record.get('request_started')
        if (type(record.get('delivery_schema')) is not int or record['delivery_schema']!=1
                or type(sequence) is not int or not 1<=sequence<=64 or phase not in TURN_PHASES
                or type(started) is not bool):
            raise ValueError('Matching delivery receipt is unsupported or malformed.')
        receipt=dict(sequence=sequence,phase=phase,request_started=started)
        if sequence in seen:
            if seen[sequence]!=receipt:raise ValueError('Conflicting delivery receipts; keep input unresolved.')
            continue  # Semantically identical duplicate evidence cannot advance the chain.
        if terminal or sequence!=len(chain)+1:
            raise ValueError('Delivery receipt chain is missing, reordered or conflicting.')
        if not chain and (phase!='preparing' or started):
            raise ValueError('Complete preparing-to-terminal evidence is unavailable in this window.')
        if chain and chain[-1]['request_started'] and not started:
            raise ValueError('Delivery request-start evidence regressed.')
        if ((phase in {'submitted','responded'} and not started) or (phase=='not_sent' and started)
                or (started and not (phase=='submitted' or chain and chain[-1]['request_started']))):
            raise ValueError('Delivery request-start evidence is inconsistent.')
        seen[sequence]=receipt
        chain.append(dict(receipt,offset=position,sha256=hashlib.sha256(raw).hexdigest()))
        terminal=phase in TERMINAL_PHASES
    if not chain or not terminal:
        raise ValueError('No complete terminal receipt chain for this exact input attempt and turn.')
    durable=seen.get(row['sequence'])
    if (not durable or durable['request_started']!=row['request_started']
            or row['phase']!='uncertain' and durable['phase']!=row['phase']
            or chain[-1]['sequence']<=row['sequence']):
        raise ValueError('Receipt chain disagrees with the durable delivery frontier.')
    material=dict(file_identity=file_id,identity=row['identity'],turn_id=row['turn_id'],chain=chain)
    version=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(version=version,identity=dict(row['identity']),turn_id=row['turn_id'],terminal=seen[chain[-1]['sequence']],
                evidence=dict(file_identity=file_id,first_offset=chain[0]['offset'],terminal_offset=chain[-1]['offset'],
                              receipt_count=len(chain),scope='Local delivery receipts, not action success or remote cancellation.'),
                coverage=dict(bytes_read=before.st_size-max(0,before.st_size-MAX_SCAN_BYTES),
                              records_scanned=len(lines),prefix_omitted=start>0,scan_start=start,scan_end=offset))
