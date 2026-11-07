import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aurora_input_recovery import InputRecovery, parse_arguments, ARCHIVE_SEGMENT_SCHEMA
from aurora_control_plane import release_info


class ArchivePreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'recovery.json'
        self.store = InputRecovery(self.path)
        self.addCleanup(self.store.close)

    def populate(self, count=3):
        identities=[]
        for n in range(count):
            identity=dict(client_id='fixture',request_id=f'input-{n}',message_id=f'message-{n}')
            self.store.admit('PRIVATE_ARCHIVE_TEXT_'+str(n),identity)
            row=self.store.snapshot()['entries'][-1]
            self.store.act(row['entry_id'],row['version'])
            identities.append(identity)
        preview=self.store.compaction_preview(0,100)
        self.store.compact(0,100,preview['version'])
        return identities

    def test_empty_legacy_preview_never_creates_file(self):
        data,preview=self.store.archive_candidate()
        self.assertEqual(data,b'')
        self.assertEqual(preview['selected_count'],0)
        self.assertEqual(preview['selection_reason'],'no_compacted_identities')
        self.assertIsNone(preview['segment_sha256'])
        self.assertFalse(self.path.exists())

    def test_canonical_bytes_and_digest_match_manifest(self):
        self.populate()
        data,preview=self.store.archive_candidate(2)
        self.assertEqual(preview['segment_bytes'],len(data))
        self.assertEqual(preview['segment_sha256'],hashlib.sha256(data).hexdigest())
        payload=json.loads(data)
        self.assertEqual(payload['schema_version'],ARCHIVE_SEGMENT_SCHEMA)
        self.assertEqual(list(payload['records']),sorted(self.store.tombstones)[:2])
        self.assertEqual(data,json.dumps(payload,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode())
        self.assertEqual(preview['omitted'],1)
        self.assertEqual(preview['hypothetical_slots_freed'],2)
        self.assertEqual(preview['actual_slots_freed'],0)

    def test_preview_cannot_write_delete_or_publish(self):
        self.populate()
        before=self.path.read_bytes(); state=self.store.snapshot(); index=copy.deepcopy(self.store.tombstones)
        with patch.object(Path,'open',side_effect=AssertionError('unexpected filesystem open')), \
             patch.object(Path,'unlink',side_effect=AssertionError('unexpected unlink')), \
             patch.object(self.store,'_publish',side_effect=AssertionError('unexpected publish')):
            preview=self.store.archive_preview()
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.store.snapshot(),state)
        self.assertEqual(self.store.tombstones,index)
        self.assertFalse(preview['archive_activation_available'])
        self.assertFalse(preview['migration_performed'])

    def test_preview_excludes_full_text_and_unresolved_input(self):
        self.populate()
        self.store.admit('UNRESOLVED_PRIVATE',dict(client_id='pending',request_id='p',message_id='p'))
        data,preview=self.store.archive_candidate()
        self.assertNotIn(b'PRIVATE',data)
        self.assertNotIn('PRIVATE',json.dumps(preview))
        self.assertEqual(preview['selected_count'],3)
        self.assertNotIn(self.store.snapshot()['entries'][0]['entry_id'],preview['selected_entry_ids'])

    def test_repeated_preview_stable_but_restart_changes_source_version(self):
        self.populate()
        data,before=self.store.archive_candidate()
        self.assertEqual((data,before),self.store.archive_candidate())
        self.store.close(); self.store=InputRecovery(self.path); self.addCleanup(self.store.close)
        other,after=self.store.archive_candidate()
        self.assertEqual(data,other)
        self.assertEqual(before['segment_sha256'],after['segment_sha256'])
        self.assertNotEqual(before['source_version'],after['source_version'])

    def test_source_change_updates_version_even_when_candidate_is_unchanged(self):
        self.populate()
        data,before=self.store.archive_candidate()
        self.store.admit('new input',dict(client_id='p',request_id='p',message_id='p'))
        other,after=self.store.archive_candidate()
        self.assertEqual(data,other)
        self.assertNotEqual(before['source_version'],after['source_version'])

    def test_preview_does_not_weaken_duplicates_or_conflicts(self):
        identities=self.populate()
        self.store.archive_preview()
        self.store.close(); self.store=InputRecovery(self.path); self.addCleanup(self.store.close)
        for n,identity in enumerate(identities):
            self.assertFalse(self.store.admit('PRIVATE_ARCHIVE_TEXT_'+str(n),identity))
            with self.assertRaises(ValueError): self.store.admit('changed',identity)

    def test_segment_size_limit_blocks_hypothetical_savings(self):
        self.populate()
        with patch('aurora_input_recovery.ARCHIVE_SEGMENT_MAX_BYTES',1):
            preview=self.store.archive_preview()
        self.assertFalse(preview['candidate_fits'])
        self.assertEqual(preview['hypothetical_slots_freed'],0)
        self.assertEqual(preview['selection_reason'],'segment_byte_limit')
        self.assertEqual(len(self.store.tombstones),3)

    def test_closed_or_corrupt_store_rejects_candidate(self):
        self.populate()
        key=next(iter(self.store.tombstones))
        self.store.tombstones[key]['text_sha256']='bad'
        with self.assertRaises(ValueError): self.store.archive_preview()
        self.store.close()
        with self.assertRaises(RuntimeError): self.store.archive_preview()

    def test_bounds_are_strict_and_readback_detached(self):
        self.assertEqual(parse_arguments('PREVIEW_INPUT_RECOVERY_ARCHIVE',[]),dict(limit=1000))
        for args in (['0'],['10001'],['2','extra'],['1.5']):
            with self.assertRaises(ValueError): parse_arguments('PREVIEW_INPUT_RECOVERY_ARCHIVE',args)
        for limit in (True,0,10001,1.5):
            with self.assertRaises(ValueError): self.store.archive_preview(limit)
        self.populate()
        view=self.store.archive_preview(); view['selected_entry_ids'].clear()
        self.assertEqual(self.store.archive_preview()['selected_count'],3)

    def test_maximum_segment_is_bounded(self):
        record=dict(text_sha256='a'*64,text_chars=10,phase='responded',attempt=1)
        self.store.schema='aurora_input_recovery_v2'
        self.store.tombstones={f'{n:064x}':dict(record) for n in range(10000)}
        data,preview=self.store.archive_candidate(10000)
        self.assertTrue(preview['candidate_fits'])
        self.assertLess(len(data),4*1024*1024)
        self.assertEqual(preview['selected_count'],10000)

    def test_release_identity_is_detached_and_matches_preview(self):
        info=release_info()
        self.assertEqual(info['release_id'],'preview-2026.11.06-r84')
        self.assertEqual(info['recovery_archive'],'preview_only')
        info['recovery_schemas'].clear()
        self.assertEqual(len(release_info()['recovery_schemas']),2)


if __name__=='__main__': unittest.main()
