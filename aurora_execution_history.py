"""Explicit immutable inspection checkpoints, never runtime restore or command replay.

Default use is session-only until Save is invoked. Capacity stops new saves;
no existing checkpoint, screenshot or unrelated file is automatically removed.
"""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid

from aurora_execution_projection import inspection_snapshot, normalize_inspection

SCHEMA = 'aurora_execution_checkpoint_v1'
MAX_BYTES = 1024 * 1024
MAX_RECORDS = 64
MAX_DIRECTORY_ENTRIES = 256
MAX_REMOVE = 16
HANDLE = re.compile(r'[0-9a-f]{32}\Z')
VERSION = re.compile(r'[0-9a-f]{64}\Z')
NOTICE = ('Historical inspection checkpoint, not live state or an event-by-event replay. '
          'Links are the latest retained evidence within this saved export. '
          'Running/queued states describe that export only; current outcome is unknown. '
          'No runtime, memory, queue or input restoration. Screenshot retention is separate.')


class HistoryError(ValueError):
    def __init__(self, status):
        self.status = status
        super().__init__(status)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')


def ordinary(path, *, directory=False):
    info = path.lstat()
    if (path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400 or
            not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise HistoryError('unsafe_path')
    return info


class ExecutionHistory:
    def __init__(self, root, *, capacity=MAX_RECORDS):
        self.root = Path(root).absolute()
        self.capacity = min(MAX_RECORDS, max(1, capacity))

    def _root(self, create=False):
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.exists():
            return False
        ordinary(self.root, directory=True)
        return True

    def _path(self, handle):
        if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
            raise HistoryError('invalid_handle')
        return self.root / (handle + '.json')

    def _inventory(self):
        records, partials, unrelated = [], 0, 0
        with os.scandir(self.root) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_DIRECTORY_ENTRIES:
                    raise HistoryError('directory_scan_limit')
                if entry.name == '.writer.lock':
                    continue
                if re.fullmatch(r'\.[0-9a-f]{32}\.[0-9a-f]{32}\.tmp', entry.name):
                    partials += 1
                elif entry.name.endswith('.json') and HANDLE.fullmatch(entry.name[:-5]):
                    records.append(entry.name[:-5])
                    if len(records) > MAX_RECORDS:
                        raise HistoryError('archive_over_capacity')
                else:
                    unrelated += 1
        return records, partials, unrelated

    @contextmanager
    def _lease(self, *, create=True):
        if not self._root(create=create):
            raise HistoryError('missing')
        path = self.root / '.writer.lock'
        try:
            handle = path.open('xb')
            handle.write(b'0'); handle.close()
        except FileExistsError:
            pass
        ordinary(path)
        handle = path.open('r+b')
        try:
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise HistoryError('writer_busy') from None
            yield
        finally:
            handle.close()

    def save(self, snapshot, *, handle=None, saved_at=None, write_id=None):
        handle = handle or uuid.uuid4().hex
        write_id = write_id or uuid.uuid4().hex
        if not isinstance(write_id, str) or not HANDLE.fullmatch(write_id):
            raise HistoryError('invalid_write_id')
        target = self._path(handle)
        clean = normalize_inspection(snapshot)
        clean.pop('notice', None)  # Display prose is not a persisted schema field.
        saved_at = time.time() if saved_at is None else saved_at
        if type(saved_at) not in (int, float) or not math.isfinite(saved_at) or saved_at <= 0:
            raise HistoryError('invalid_timestamp')
        payload = dict(schema=SCHEMA, checkpoint_id=handle, saved_at_epoch=saved_at, inspection=clean)
        document = dict(payload, sha256=hashlib.sha256(canonical(payload)).hexdigest())
        data = canonical(document)
        if len(data) > MAX_BYTES:
            raise HistoryError('snapshot_too_large')
        with self._lease():
            if target.exists():
                old = self.load(handle)
                if {key: value for key, value in old['inspection'].items() if key != 'notice'} == clean:
                    return dict(status='already_saved', checkpoint_id=handle, saved_at_epoch=old['saved_at_epoch'])
                raise HistoryError('handle_conflict')
            records, _, _ = self._inventory()
            if len(records) >= self.capacity:
                raise HistoryError('capacity_reached')
            temporary = self.root / ('.' + handle + '.' + write_id + '.tmp')
            owns = False
            try:
                with temporary.open('xb') as output:
                    owns = True
                    output.write(data); output.flush(); os.fsync(output.fileno())
                # Publish once without replacing an existing immutable checkpoint.
                os.link(temporary, target)
            finally:
                if owns:
                    temporary.unlink(missing_ok=True)
        return dict(status='saved', checkpoint_id=handle, saved_at_epoch=saved_at)

    def load(self, handle):
        path = self._path(handle)
        if not self._root():
            raise HistoryError('missing')
        try:
            before = ordinary(path)
            if before.st_size > MAX_BYTES:
                raise HistoryError('record_too_large')
            with path.open('rb') as source:
                opened = os.fstat(source.fileno())
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise HistoryError('changed_during_read')
                raw = source.read(MAX_BYTES + 1)
                after = os.fstat(source.fileno())
            final = ordinary(path)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
            if len(raw) > MAX_BYTES or identity(before) != identity(after) or identity(after) != identity(final):
                raise HistoryError('changed_during_read')
            value = json.loads(raw)
            if not isinstance(value, dict) or value.get('schema') != SCHEMA:
                raise HistoryError('unsupported_schema')
            if set(value) != {'schema', 'checkpoint_id', 'saved_at_epoch', 'inspection', 'sha256'} or value['checkpoint_id'] != handle:
                raise HistoryError('invalid_record')
            saved_at = value['saved_at_epoch']
            if type(saved_at) not in (int, float) or not math.isfinite(saved_at) or saved_at <= 0:
                raise HistoryError('invalid_record')
            payload = {key: item for key, item in value.items() if key != 'sha256'}
            if hashlib.sha256(canonical(payload)).hexdigest() != value['sha256']:
                raise HistoryError('checksum_mismatch')
            clean = normalize_inspection(value['inspection'])
            if {key: item for key, item in clean.items() if key != 'notice'} != value['inspection']:
                raise HistoryError('invalid_projection')
            return dict(status='loaded', checkpoint_id=handle, saved_at_epoch=saved_at,
                        inspection=clean, notice=NOTICE, integrity='checksum_matches_not_a_signature')
        except FileNotFoundError:
            raise HistoryError('missing') from None
        except (TypeError, json.JSONDecodeError, UnicodeDecodeError):
            raise HistoryError('corrupt') from None

    def list(self):
        if not self._root():
            return dict(status='listed', records=[], capacity=self.capacity, partial_files=0, unrelated_files=0)
        handles, partials, unrelated = self._inventory()
        rows = []
        for handle in handles:
            try:
                value = self.load(handle)
                task = value['inspection']['task']
                rows.append(dict(checkpoint_id=handle, status='available', saved_at_epoch=value['saved_at_epoch'],
                    task_id=task['task_id'], recorded_task_status=task.get('status', 'unknown')))
            except (HistoryError, OSError, ValueError) as error:
                rows.append(dict(checkpoint_id=handle, status=error.status if isinstance(error, HistoryError) else 'unreadable'))
        rows.sort(key=lambda row: (row.get('saved_at_epoch', 0), row['checkpoint_id']), reverse=True)
        return dict(status='listed', records=rows, capacity=self.capacity, partial_files=partials, unrelated_files=unrelated,
                    retention='Stop at capacity; no automatic eviction. Partial and unrelated files are not deleted.')

    @staticmethod
    def _file_identity(info):
        return [info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns,
                info.st_ctime_ns, getattr(info, 'st_file_attributes', 0)]

    def _retention_state(self):
        """Bounded archive version; content hashes for checkpoint-shaped regular files.

        Caller holds the cooperative writer lease. Unknown entries are inventoried
        without opening them. This is not protection against hostile local writers.
        """
        root = ordinary(self.root, directory=True)
        def inventory():
            rows = {}
            with os.scandir(self.root) as entries:
                for index, entry in enumerate(entries):
                    if index >= MAX_DIRECTORY_ENTRIES:
                        raise HistoryError('directory_scan_limit')
                    if entry.name != '.writer.lock':
                        # Windows DirEntry.stat can omit inode/device identity.
                        rows[entry.name] = self._file_identity((self.root / entry.name).lstat())
            return rows
        before = inventory()
        manifest = {}
        for name, identity in before.items():
            row = dict(identity=identity)
            if (name.endswith('.json') and HANDLE.fullmatch(name[:-5]) and
                    stat.S_ISREG(identity[2]) and not identity[6] & 0x400 and identity[3] <= MAX_BYTES):
                path = self.root / name
                with path.open('rb') as source:
                    opened = self._file_identity(os.fstat(source.fileno()))
                    # CPython/Windows path-stat and fd-stat can disagree on ctime
                    # after hard-link publication. Compare common identity fields;
                    # keep the full path-stat identity in the archive version.
                    if opened[:5] + opened[6:] != identity[:5] + identity[6:]:
                        raise HistoryError('changed_during_read')
                    raw = source.read(MAX_BYTES + 1)
                    if len(raw) > MAX_BYTES or self._file_identity(os.fstat(source.fileno())) != opened:
                        raise HistoryError('changed_during_read')
                row['sha256'] = hashlib.sha256(raw).hexdigest()
            manifest[name] = row
        final_root = ordinary(self.root, directory=True)
        if before != inventory() or (root.st_dev, root.st_ino) != (final_root.st_dev, final_root.st_ino):
            raise HistoryError('changed_during_read')
        version = hashlib.sha256(canonical(dict(root=[root.st_dev, root.st_ino], entries=manifest))).hexdigest()
        return version, manifest

    def _removal_handles(self, handles):
        if not isinstance(handles, list) or not 1 <= len(handles) <= MAX_REMOVE:
            raise HistoryError('invalid_selection')
        for handle in handles:
            self._path(handle)
        if len(set(handles)) != len(handles):
            raise HistoryError('duplicate_selection')
        return sorted(handles)

    @staticmethod
    def _removal_version(version, handles):
        return hashlib.sha256(canonical(dict(store_version=version, checkpoint_ids=handles))).hexdigest()

    def preview_remove(self, handles):
        """Describe only explicit, valid checkpoint selections; no content is removed."""
        handles = self._removal_handles(handles)
        with self._lease(create=False):
            version, manifest = self._retention_state()
            selected = []
            for handle in handles:
                if handle+'.json' not in manifest:
                    raise HistoryError('missing')
                record = self.load(handle)  # Corrupt/unknown formats cannot be removed here.
                selected.append(dict(checkpoint_id=handle, task_id=record['inspection']['task']['task_id'],
                    saved_at_epoch=record['saved_at_epoch'], source_export=record['inspection'].get('source_export', {}),
                    bytes=manifest[handle+'.json']['identity'][3]))
            if self._retention_state()[0] != version:
                raise HistoryError('version_conflict')
            return dict(status='removal_preview', expected_version=self._removal_version(version, handles),
                        store_version=version, checkpoint_ids=handles,
                        selected=selected, total_bytes=sum(row['bytes'] for row in selected),
                        notice='Permanently removes only these saved inspection files. No undo. Screenshots, live runtime and the loaded view are unchanged.')

    def remove(self, handles, expected_version, *, confirm=False):
        """Explicit version-checked removal, with exact partial/uncertain outcomes."""
        handles = self._removal_handles(handles)
        if confirm is not True:
            raise HistoryError('confirmation_required')
        if not isinstance(expected_version, str) or not VERSION.fullmatch(expected_version):
            raise HistoryError('invalid_version')
        with self._lease(create=False):
            version, manifest = self._retention_state()
            if self._removal_version(version, handles) != expected_version:
                raise HistoryError('version_conflict')
            for handle in handles:
                self.load(handle)
            if self._retention_state()[0] != version:
                raise HistoryError('version_conflict')
            removed = []
            for index, handle in enumerate(handles):
                path = self._path(handle)
                try:
                    # Exact child path and identity, not a user path or wildcard.
                    ordinary(self.root, directory=True)
                    if path.resolve(strict=True).parent != self.root.resolve(strict=True):
                        raise HistoryError('unsafe_path')
                    if self._file_identity(ordinary(path)) != manifest[handle+'.json']['identity']:
                        raise HistoryError('changed_during_remove')
                except (OSError, HistoryError):
                    return dict(status='removal_partial' if removed else 'version_conflict',
                        removed=removed, uncertain=[], not_attempted=handles[index:], checkpoint_ids=handles,
                        before_version=version, reason='selected_file_changed_or_unreadable')
                try:
                    path.unlink()
                except OSError:
                    return dict(status='removal_partial' if removed else 'removal_uncertain',
                        removed=removed, uncertain=[handle], not_attempted=handles[index+1:], checkpoint_ids=handles,
                        before_version=version, reason='file_removal_failed_or_unacknowledged')
                removed.append(handle)
            return dict(status='removed', removed=removed, uncertain=[], not_attempted=[],
                        checkpoint_ids=handles, before_version=version)


def history_action(root, request):
    """One bounded operation; failures never execute or restore a runtime task."""
    operation = request.get('operation')
    handle = request.get('checkpoint_id')
    try:
        store = ExecutionHistory(root)
        if operation == 'save':
            if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
                raise HistoryError('invalid_handle')
            return store.save(request.get('inspection'), handle=handle, saved_at=request.get('saved_at_epoch'), write_id=request.get('write_id'))
        if operation == 'list':
            return store.list()
        if operation == 'load':
            return store.load(handle)
        if operation == 'preview_remove':
            return store.preview_remove(request.get('checkpoint_ids'))
        if operation == 'remove':
            return store.remove(request.get('checkpoint_ids'), request.get('expected_version'), confirm=request.get('confirm'))
        raise HistoryError('invalid_operation')
    except HistoryError as error:
        return dict(status=error.status, checkpoint_id=handle)
    except (ValueError, TypeError, OverflowError):
        return dict(status='invalid_snapshot', checkpoint_id=handle)
    except OSError:
        return dict(status='save_uncertain' if operation == 'save' else 'removal_uncertain' if operation == 'remove' else 'unreadable',
                    checkpoint_id=handle, checkpoint_ids=request.get('checkpoint_ids', []))


def main():
    root = Path(__file__).resolve().parent
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        try:
            raw = sys.stdin.buffer.read(MAX_BYTES + 8193)
            if len(raw) > MAX_BYTES + 8192:
                raise ValueError('too large')
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise ValueError('invalid request')
            result = history_action(sys.argv[2], request)
        except (ValueError, TypeError):
            result = dict(status='invalid_request')
    else:
        import argparse
        parser = argparse.ArgumentParser(description=NOTICE)
        parser.add_argument('operation', choices=('save', 'list', 'load', 'preview-remove', 'remove'))
        parser.add_argument('checkpoint_ids', nargs='*')
        parser.add_argument('--expected-version')
        parser.add_argument('--confirm', action='store_true', help='Acknowledge permanent removal of the previewed selection.')
        args = parser.parse_args()
        if (args.operation in ('save', 'list') and args.checkpoint_ids or
                args.operation == 'load' and len(args.checkpoint_ids) != 1 or
                args.operation != 'remove' and (args.expected_version or args.confirm)):
            parser.error('Arguments do not match this operation.')
        request = dict(operation=args.operation.replace('-', '_'), checkpoint_id=next(iter(args.checkpoint_ids), None),
                       checkpoint_ids=args.checkpoint_ids, expected_version=args.expected_version, confirm=args.confirm)
        if args.operation == 'save':
            try:
                with (root / 'aurora_control_panel_state.json').open('rb') as source:
                    raw = source.read(8 * MAX_BYTES + 1)
                if len(raw) > 8 * MAX_BYTES:
                    raise ValueError('state too large')
                request.update(checkpoint_id=uuid.uuid4().hex, saved_at_epoch=time.time(),
                               inspection=inspection_snapshot(json.loads(raw)))
            except (OSError, ValueError):
                print(json.dumps({'status':'state_unavailable'})); return
        result = history_action(root / 'execution_history', request)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
