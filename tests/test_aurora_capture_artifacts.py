import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image
import aurora_capture_artifacts as artifacts
from aurora_capture_store import save_capture
from aurora_capture_provenance import CaptureService


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aurora-artifact-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = Path(save_capture(Image.new('RGB', (8, 6), 'blue'), self.root))
        self.frame_id = 'a' * 32
        self.reference = artifacts.capture_reference(self.path, self.frame_id, self.root)

    def frame(self):
        return dict(path=str(self.path), provenance={'frame_id': self.frame_id}, artifact=copy.deepcopy(self.reference))

    def test_full_file_reference_without_path_or_pixels(self):
        self.assertEqual(self.reference['status'], 'published')
        self.assertEqual(self.reference['sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertNotIn(str(self.root), json.dumps(self.reference))
        self.assertEqual(artifacts.check_artifact(self.root, self.reference)['status'], 'available')

    def test_encoding_binds_same_source_bytes_and_actual_png(self):
        evidence = {}
        payload = artifacts.encode_image(self.path, evidence)
        ref = artifacts.prepared_reference(self.frame(), str(self.path), evidence)
        self.assertEqual(ref['status'], 'bound')
        self.assertEqual(ref['encoded_png_sha256'], hashlib.sha256(base64.b64decode(payload)).hexdigest())
        with Image.open(io.BytesIO(base64.b64decode(payload))) as image:
            self.assertEqual(image.getpixel((0, 0)), (0, 0, 255))

    def test_mutated_source_before_preparation_never_claims_original_frame_bytes(self):
        Image.new('RGB', (8, 6), 'red').save(self.path)
        evidence = {}
        self.assertTrue(artifacts.encode_image(self.path, evidence))
        ref = artifacts.prepared_reference(self.frame(), str(self.path), evidence)
        self.assertEqual(ref['status'], 'source_changed')
        self.assertEqual(artifacts.check_artifact(self.root, ref)['status'], 'changed')

    def test_missing_file_does_not_choose_another_screenshot(self):
        self.path.unlink()
        save_capture(Image.new('RGB', (8, 6), 'blue'), self.root)
        self.assertEqual(artifacts.check_artifact(self.root, self.reference)['status'], 'missing')

    def test_mutation_after_preparation_and_suffix_tampering_detected(self):
        # Same first bytes: this is a full-file hash, not the old prefix fingerprint.
        self.path.write_bytes(self.path.read_bytes() + b'changed-tail')
        self.assertEqual(artifacts.check_artifact(self.root, self.reference)['status'], 'changed')

    def test_traversal_absolute_ads_and_arbitrary_names_never_open(self):
        for name in ('../secret.png', 'C:/secret.png', 'https://example.com/a.png', 'a.png:secret', 'older.png', 'a'*200):
            with self.subTest(name=name), patch.object(artifacts, 'read_bounded', side_effect=AssertionError('must not open')):
                ref = dict(self.reference, artifact_name=name)
                self.assertEqual(artifacts.check_artifact(self.root, ref)['status'], 'invalid_reference')

    def test_malformed_or_cross_frame_reference_not_bound(self):
        evidence = {}
        artifacts.encode_image(self.path, evidence)
        for frame in (None, {}, dict(self.frame(), path='different.png')):
            self.assertEqual(artifacts.prepared_reference(frame, str(self.path), evidence), {})
        frame = self.frame()
        frame['provenance']['frame_id'] = 'b'*32
        self.assertEqual(artifacts.prepared_reference(frame, str(self.path), evidence)['status'], 'unavailable')
        for field, value in [('frame_id', 'invalid'), ('byte_count', True), ('sha256', 'bad'), ('byte_count', artifacts.MAX_BYTES+1)]:
            self.assertEqual(artifacts.check_artifact(self.root, dict(self.reference, **{field:value}))['status'], 'invalid_reference')

    def test_old_capture_is_explicitly_unknown(self):
        frame = self.frame()
        frame.pop('artifact')
        self.assertEqual(artifacts.prepared_reference(frame, str(self.path), {})['reason'], 'no_exact_published_reference')

    def test_oversized_evidence_does_not_remove_legacy_encoding(self):
        with patch.object(artifacts, 'MAX_BYTES', 4):
            self.assertEqual(artifacts.capture_reference(self.path, self.frame_id, self.root)['reason'], 'too_large')
            evidence = {}
            self.assertTrue(artifacts.encode_image(self.path, evidence))
            self.assertEqual(evidence['reason'], 'too_large')

    def test_unknown_fields_and_private_values_not_carried(self):
        reference = dict(self.reference, path='PRIVATE_PATH', pixels='PRIVATE_PIXELS', api_key='FAKE_PRIVATE_KEY')
        self.assertNotIn('PRIVATE', json.dumps(artifacts.safe_reference(reference)))
        self.assertNotIn('PRIVATE', json.dumps(artifacts.check_artifact(self.root, reference)))

    def test_unreadable_and_file_changed_during_read_reported(self):
        with patch.object(artifacts, 'read_bounded', side_effect=PermissionError('PRIVATE_PATH')):
            result = artifacts.check_artifact(self.root, self.reference)
            self.assertEqual(result['status'], 'unreadable')
            self.assertNotIn('PRIVATE', json.dumps(result))
        with patch.object(artifacts, 'read_bounded', return_value=(None, 'changed_during_read')):
            self.assertEqual(artifacts.check_artifact(self.root, self.reference)['status'], 'changed_during_read')

    def test_links_refused_even_to_sibling_capture(self):
        with patch.object(Path, 'is_symlink', return_value=True):
            self.assertEqual(artifacts.check_artifact(self.root, self.reference)['status'], 'unsafe_file')

    def test_service_preserves_reference_by_value_and_legacy_publish(self):
        service = CaptureService()
        stamp = service.finish(service.begin('fixture'))
        ref = dict(self.reference, frame_id=stamp.frame_id)
        self.assertTrue(service.publish(stamp, path=str(self.path), timestamp='', capture_hash='', counter=1, artifact=ref))
        ref['sha256'] = 'changed'
        self.assertEqual(service.snapshot()['latest']['artifact']['sha256'], self.reference['sha256'])
        stamp = service.finish(service.begin('legacy'))
        self.assertTrue(service.publish(stamp, path=str(self.path), timestamp='', capture_hash='', counter=2))
        self.assertEqual(service.snapshot()['latest']['artifact'], {})

    def test_owned_checker_completes_and_reaps_process(self):
        job = artifacts.ArtifactCheck(self.root, self.reference)
        self.addCleanup(job.cancel)
        deadline = time.monotonic() + 10
        result = job.poll()
        while result is None and time.monotonic() < deadline:
            time.sleep(.02)
            result = job.poll()
        self.assertEqual(result['status'], 'available')
        self.assertIsNotNone(job.process.poll())
        self.assertTrue(job.process.stdout.closed)

    def test_timeout_and_cancel_reap_checker_and_remain_terminal(self):
        class FakeProcess:
            stdin, stdout = None, None
            stopped = False
            def poll(self): return 1 if self.stopped else None
            def terminate(self): self.stopped = True
            def wait(self, timeout=None): return 1
        job = object.__new__(artifacts.ArtifactCheck)
        job.process, job.result, job.clock, job.deadline = FakeProcess(), None, lambda: 10, 5
        self.assertEqual(job.poll()['status'], 'timed_out')
        self.assertTrue(job.process.stopped)
        self.assertEqual(job.poll()['status'], 'timed_out')
        real = artifacts.ArtifactCheck(self.root, self.reference)
        self.assertEqual(real.cancel()['status'], 'cancelled')
        self.assertIsNotNone(real.process.poll())
        self.assertTrue(real.process.stdout.closed)


if __name__ == '__main__':
    unittest.main()
