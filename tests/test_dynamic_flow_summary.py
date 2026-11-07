import unittest
from analyze_horizons_trial import dynamic_flow_summary


class DynamicFlowSummaryTests(unittest.TestCase):
    def fixture(self):
        events = [dict(event='request_started', request_id='r1', at=10, frame_id='f1'),
                  dict(event='request_finished', request_id='r1', at=15),
                  dict(event='request_started', request_id='r2', at=18, frame_id='f2')]
        chat = [dict(event='model_request', inference_request_id='r1', wake_reason='user_input'),
                dict(event='model_request', inference_request_id='r2', wake_reason='command_result,capture_tick')]
        frames = [dict(capture=dict(provenance=dict(frame_id='f1', status='acquired', acquired_end_epoch=9))),
                  dict(capture=dict(provenance=dict(frame_id='f2', status='acquired', acquired_end_epoch=17)))]
        return events, chat, frames

    def test_exact_join_and_local_gap(self):
        report = dynamic_flow_summary(*self.fixture())
        self.assertEqual(report['request_complete_to_next_start_seconds']['median'], 3)
        self.assertEqual(report['selected_frame_end_to_request_start_seconds']['median'], 1)
        self.assertEqual(report['wake_reasons']['command_result,capture_tick'], 1)

    def test_missing_and_wrong_frames_do_not_join_by_time(self):
        events, chat, frames = self.fixture()
        frames[1]['capture']['provenance']['frame_id'] = 'unrelated'
        report = dynamic_flow_summary(events, chat[:1], frames)
        self.assertEqual(report['unknown_selected_frame_ages'], 1)
        self.assertEqual(report['missing_or_ambiguous_request_metadata'], 1)

    def test_duplicates_are_ambiguous_not_last_writer_wins(self):
        events, chat, frames = self.fixture()
        events.append(dict(event='request_finished', request_id='r1', at=16))
        report = dynamic_flow_summary(events, chat+chat[:1], frames+frames[:1])
        self.assertEqual(report['unknown_continuation_gaps'], 1)
        self.assertEqual(report['ambiguous_frame_identities'], 1)
        self.assertEqual(report['unknown_selected_frame_ages'], 1)
        self.assertEqual(report['missing_or_ambiguous_request_metadata'], 1)

    def test_invalid_clock_evidence_stays_unknown(self):
        for invalid in (None, True, float('nan'), float('inf'), '9', 11):
            events, chat, frames = self.fixture()
            frames[0]['capture']['provenance']['acquired_end_epoch'] = invalid
            self.assertEqual(dynamic_flow_summary(events, chat, frames)['unknown_selected_frame_ages'], 1)

    def test_image_free_readback_is_not_missing_frame_error(self):
        events, chat, frames = self.fixture()
        events[2]['frame_id'] = ''
        chat[1]['wake_reason'] = 'command_readback'
        report = dynamic_flow_summary(events, chat, frames)
        self.assertEqual(report['requests_without_recorded_frame_id'], 1)
        self.assertEqual(report['unknown_selected_frame_ages'], 0)
        self.assertEqual(report['wake_reasons']['command_readback'], 1)

    def test_repeated_frame_is_counted_without_claiming_staleness(self):
        events, chat, frames = self.fixture()
        events[2]['frame_id'] = 'f1'
        report = dynamic_flow_summary(events, chat, frames)
        self.assertEqual(report['repeated_selected_frame_uses'], 1)
        self.assertEqual(report['selected_distinct_frames'], 1)
        self.assertEqual(dynamic_flow_summary([], [], [])['selected_frame_end_to_request_start_seconds']['median'], None)


if __name__ == '__main__':
    unittest.main()
