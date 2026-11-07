"""Bounded local capture integrity evidence; no capture, input or provider calls.

References contain a generated basename, never an arbitrary path. File integrity
is distinct from visual truth, provider receipt and semantic action success.
"""
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time


MAX_BYTES = 32 * 1024 * 1024
SCHEMA = 'aurora_capture_artifact_v1'
FIELDS = ('schema', 'status', 'frame_id', 'artifact_name', 'byte_count', 'sha256',
          'source_sha256_at_preparation', 'encoded_png_sha256', 'reason')
NAME = re.compile(r'[0-9]{1,24}-[0-9a-f]{32}\.png\Z')
HEX32 = re.compile(r'[0-9a-f]{32}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')


def safe_reference(value):
    """Allowlist metadata without retaining user paths, pixels or extra fields."""
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in FIELDS if key in value and
            (type(value[key]) is int or isinstance(value[key], str) and len(value[key]) <= 160)}


def valid_reference(ref):
    return (isinstance(ref, dict) and ref.get('schema') == SCHEMA
            and bool(NAME.fullmatch(str(ref.get('artifact_name', ''))))
            and bool(HEX32.fullmatch(str(ref.get('frame_id', ''))))
            and bool(HEX64.fullmatch(str(ref.get('sha256', ''))))
            and type(ref.get('byte_count')) is int and 0 < ref['byte_count'] <= MAX_BYTES)


def read_bounded(path):
    """Read a regular local file once; reject links and metadata changes."""
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or path.is_symlink() or
            getattr(before, 'st_file_attributes', 0) & 0x400):
        return None, 'unsafe_file'
    if before.st_size > MAX_BYTES:
        return None, 'too_large'
    with path.open('rb') as source:
        opened = os.fstat(source.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            return None, 'changed_during_read'
        data = source.read(MAX_BYTES + 1)
        after = os.fstat(source.fileno())
    final = path.lstat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if len(data) > MAX_BYTES:
        return None, 'too_large'
    if identity(before) != identity(after) or identity(after) != identity(final):
        return None, 'changed_during_read'
    return data, ''


def capture_reference(path, frame_id, root):
    """Record full-file identity at publication, without failing legacy capture."""
    result = dict(schema=SCHEMA, status='unavailable', frame_id=str(frame_id)[:160])
    try:
        path, root = Path(path), Path(root).resolve()
        if not HEX32.fullmatch(str(frame_id)) or not NAME.fullmatch(path.name) or path.resolve().parent != root:
            return dict(result, reason='unrecognized_capture')
        data, failure = read_bounded(path)
        if failure:
            return dict(result, reason=failure)
        return dict(result, status='published', artifact_name=path.name, byte_count=len(data),
                    sha256=hashlib.sha256(data).hexdigest())
    except OSError:
        return dict(result, reason='unreadable')


def encode_image(path, evidence=None):
    """Preserve PNG encoding; optionally hash the same bytes that Pillow reads."""
    from PIL import Image
    data, failure = (read_bounded(Path(path)) if evidence is not None else (None, ''))
    if evidence is not None:
        evidence.clear()
        evidence.update(status='unavailable', reason=failure or 'not_encoded')
    with Image.open(io.BytesIO(data) if data is not None else path) as image:
        buffered = io.BytesIO()
        image.save(buffered, format='PNG')
        encoded = buffered.getvalue()
    if evidence is not None and data is not None:
        evidence.update(status='encoded', reason='', byte_count=len(data),
                        source_sha256_at_preparation=hashlib.sha256(data).hexdigest(),
                        encoded_png_sha256=hashlib.sha256(encoded).hexdigest())
    return base64.b64encode(encoded).decode('utf-8')


def prepared_reference(frame, image_path, encoding):
    """Bind published source bytes and actual encoded PNG to one selected frame."""
    if not isinstance(frame, dict) or frame.get('path') != image_path:
        return {}
    ref = safe_reference(frame.get('artifact'))
    if not valid_reference(ref) or ref['frame_id'] != frame.get('provenance', {}).get('frame_id'):
        return dict(schema=SCHEMA, status='unavailable', reason='no_exact_published_reference')
    ref.update(status='unavailable', reason=encoding.get('reason') or 'encoding_evidence_missing')
    if (encoding.get('status') == 'encoded' and
            all(HEX64.fullmatch(str(encoding.get(key, ''))) for key in ('source_sha256_at_preparation', 'encoded_png_sha256'))):
        for key in ('source_sha256_at_preparation', 'encoded_png_sha256'):
            ref[key] = encoding[key]
        matches = encoding.get('byte_count') == ref['byte_count'] and encoding['source_sha256_at_preparation'] == ref['sha256']
        ref.update(status='bound' if matches else 'source_changed', reason='' if matches else 'source_changed_before_preparation')
    return ref


def check_artifact(root, reference):
    """Check only an exact generated file within the caller-selected local root."""
    ref = safe_reference(reference)
    result = dict(schema='aurora_capture_artifact_check_v1', checked_at_epoch=time.time(),
                  status='invalid_reference', frame_id=ref.get('frame_id', ''),
                  meaning='Local file integrity only; no visual outcome or provider-receipt proof.')
    if not valid_reference(ref):
        return result
    result.update(artifact_name=ref['artifact_name'], expected_sha256=ref['sha256'])
    try:
        root = Path(root).resolve()
        candidate = root / ref['artifact_name']
        if candidate.resolve().parent != root:
            return dict(result, status='unsafe_file')
        data, failure = read_bounded(candidate)
        if failure:
            return dict(result, status=failure)
        digest = hashlib.sha256(data).hexdigest()
        return dict(result, status='available' if digest == ref['sha256'] and len(data) == ref['byte_count'] else 'changed',
                    observed_sha256=digest, observed_byte_count=len(data))
    except FileNotFoundError:
        return dict(result, status='missing')
    except OSError:
        return dict(result, status='unreadable')


class ArtifactCheck:
    """One hidden owned checker, with bounded input/output and a parent deadline."""
    def __init__(self, root, reference, *, timeout=8, clock=time.monotonic):
        self.started_at_epoch = time.time()
        self.clock, self.deadline = clock, clock() + timeout
        self.process, self.result = None, None
        payload = json.dumps(safe_reference(reference))
        try:
            self.process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--check', str(root)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.process.stdin.write(payload)
            self.process.stdin.close()
            self.process.stdin = None
        except OSError:
            self.cancel('unavailable')

    def poll(self):
        if self.result is not None:
            return copy.deepcopy(self.result)
        if self.process.poll() is None:
            if self.clock() >= self.deadline:
                return self.cancel('timed_out')
            return None
        try:
            output, _ = self.process.communicate(timeout=0.2)
            result = json.loads(output) if len(output) <= 4096 and self.process.returncode == 0 else None
            self.result = result if isinstance(result, dict) else {'status': 'unavailable', 'checked_at_epoch': time.time()}
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return self.cancel('unavailable')
        return copy.deepcopy(self.result)

    def cancel(self, status='cancelled'):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None:
                    stream.close()
        self.result = {'status': status, 'checked_at_epoch': time.time()}
        return copy.deepcopy(self.result)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--check':
        try:
            reference = json.loads(sys.stdin.read(4097))
            print(json.dumps(check_artifact(sys.argv[2], reference)))
        except (ValueError, TypeError):
            print(json.dumps({'status': 'invalid_reference'}))
