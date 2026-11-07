import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aurora_input_recovery import InputRecovery, identity_key


class RecoveryCapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'recovery.json'
        self.open()

    def open(self):
        self.store = InputRecovery(self.path, max_rows=4, max_tombstones=3)
        self.addCleanup(self.store.close)

    def identity(self, n):
        return dict(client_id='capacity-fixture', request_id=f'input-{n}', message_id=f'message-{n}')

    def terminal(self, n):
        identity = self.identity(n)
        self.store.admit(f'Private fixture text {n}', identity)
        row = self.store.snapshot()['entries'][-1]
        self.store.act(row['entry_id'], row['version'])
        return identity

    def compact(self, keep=0, limit=100):
        preview = self.store.compaction_preview(keep, limit)
        return self.store.compact(keep, limit, preview['version'])

    def test_new_store_capacity_inspection_does_not_write_or_serialize(self):
        with patch('aurora_input_recovery.json.dumps', side_effect=AssertionError('inspection serialized')):
            state = self.store.summary()['capacity']
        self.assertEqual(state['retained_available'], 4)
        self.assertEqual(state['deduplication_available'], 3)
        self.assertFalse(state['archive_rollover_available'])
        self.assertFalse(self.path.exists())

    def test_cached_bytes_match_ascii_serialization_not_character_count(self):
        self.store.admit('Pokémon 🐉', self.identity(1))
        state = self.store.capacity_summary()
        self.assertEqual(state['snapshot_bytes'], len(self.path.read_bytes()))
        self.assertEqual(state['new_input_capacity'], 'payload_dependent')
        self.assertNotIn('Pokémon', json.dumps(state))

    def test_loaded_noncanonical_file_reports_canonical_snapshot_size(self):
        self.terminal(1)
        self.store.close()
        data = json.loads(self.path.read_text())
        self.path.write_text(json.dumps(data, indent=8))
        self.open()
        size = self.store.capacity_summary()['snapshot_bytes']
        self.assertEqual(size, len(json.dumps(data, ensure_ascii=True, allow_nan=False).encode()))
        self.assertLess(size, self.path.stat().st_size)

    def test_full_index_does_not_block_remaining_payload_slots(self):
        for n in range(3): self.terminal(n)
        self.compact()
        self.store.admit('New pending work', self.identity(9))
        state = self.store.capacity_summary()
        self.assertEqual(state['deduplication_available'], 0)
        self.assertEqual(state['retained_available'], 3)
        self.assertEqual(state['new_input_capacity'], 'payload_dependent')
        self.assertEqual(state['protected_payloads'], 1)

    def test_full_index_explains_zero_compaction_without_dropping_identity(self):
        for n in range(3): self.terminal(n)
        self.compact()
        self.terminal(8)
        before = self.path.read_bytes()
        preview = self.store.compaction_preview(0,100)
        self.assertEqual(preview['selection_reason'], 'deduplication_limit')
        self.assertTrue(preview['capacity_blocked'])
        result = self.compact()
        self.assertEqual(result['compacted_count'], 0)
        self.assertEqual(result['selection_reason'], 'deduplication_limit')
        self.assertTrue(result['capacity_blocked'])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.store.admit('Private fixture text 0', self.identity(0)))

    def test_preview_distinguishes_retention_batch_and_index_constraints(self):
        self.assertEqual(self.store.compaction_preview()['selection_reason'], 'no_eligible_terminal_inputs')
        for n in range(4): self.terminal(n)
        self.assertEqual(self.store.compaction_preview(4,100)['selection_reason'], 'retention_floor')
        self.assertEqual(self.store.compaction_preview(0,1)['selection_reason'], 'batch_limit')
        self.assertEqual(self.store.compaction_preview(0,3)['selection_reason'], 'batch_and_index_limit')
        self.assertEqual(self.store.compaction_preview(0,4)['selection_reason'], 'deduplication_limit')
        self.assertEqual(self.store.compaction_preview(1,4)['selection_reason'], 'all_candidates_selected')

    def test_both_limits_preserve_duplicates_and_conflicts_across_restart(self):
        for n in range(3): self.terminal(n)
        self.compact()
        for n in range(3,7): self.terminal(n)
        before = self.path.read_bytes()
        with self.assertRaises(ValueError): self.store.admit('Rejected', self.identity(9))
        self.assertEqual(self.path.read_bytes(), before)
        self.store.close(); self.open()
        self.assertEqual(self.store.capacity_summary()['new_input_capacity'], 'retained_limit')
        for n in range(7):
            self.assertFalse(self.store.admit(f'Private fixture text {n}',self.identity(n)))
            with self.assertRaises(ValueError): self.store.admit('Changed',self.identity(n))

    def test_byte_exhaustion_preserves_memory_disk_and_cached_size(self):
        self.terminal(1)
        before = self.path.read_bytes()
        summary = self.store.summary()
        with patch('aurora_input_recovery.MAX_BYTES', len(before)+1):
            self.assertEqual(self.store.capacity_summary()['new_input_capacity'], 'payload_dependent')
            with self.assertRaisesRegex(ValueError, 'document full'):
                self.store.admit('🐉'*100, self.identity(2))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.summary(), summary)

    def test_exact_byte_limit_is_reported_without_claiming_disk_failure(self):
        self.terminal(1)
        with patch('aurora_input_recovery.MAX_BYTES', self.store.serialized_bytes):
            state = self.store.capacity_summary()
            self.assertEqual(state['snapshot_bytes_available'], 0)
            self.assertEqual(state['new_input_capacity'], 'byte_limit')

    def test_fsync_and_replace_failure_preserve_capacity_and_evidence(self):
        self.terminal(1)
        for boundary in ('os.fsync', 'os.replace'):
            before, state = self.path.read_bytes(), self.store.summary()
            with patch('aurora_input_recovery.'+boundary, side_effect=OSError('fixture disk failure')):
                with self.assertRaises(OSError): self.compact()
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(self.store.summary(), state)
            self.assertFalse(list(self.path.parent.glob('.aurora-input-*.tmp')))

    def test_successful_replace_does_not_run_redundant_cleanup_after_commit(self):
        self.terminal(1)
        with patch.object(Path, 'unlink', side_effect=OSError('cleanup would fail after commit')):
            result = self.compact()
        self.assertEqual(result['compacted_count'], 1)
        self.assertEqual(self.store.serialized_bytes, len(self.path.read_bytes()))
        self.assertIn(identity_key(self.identity(1)), self.store.tombstones)

    def test_concurrent_previews_cannot_both_spend_last_index_slot(self):
        from concurrent.futures import ThreadPoolExecutor
        for n in range(2): self.terminal(n)
        self.compact()
        for n in range(2,4): self.terminal(n)
        preview = self.store.compaction_preview(0,1)
        def apply():
            try: return self.store.compact(0,1,preview['version'])['compacted_count']
            except ValueError: return 'stale'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:apply(), range(2)))
        self.assertCountEqual(results,[1,'stale'])
        self.assertEqual(self.store.capacity_summary()['deduplication_available'],0)
        self.assertEqual(self.store.capacity_summary()['retained_used'],1)


if __name__ == '__main__': unittest.main()
