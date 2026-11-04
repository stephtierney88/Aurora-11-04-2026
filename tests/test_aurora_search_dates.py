"""Calendar and exact-boundary regressions for R2a2; no provider/native I/O."""
import datetime as dt
import unittest
from unittest.mock import patch

import aurora_search_query as search


def window(**options):
    return search.compile_search_filter(options)["dates"]


class DateConvenienceTests(unittest.TestCase):
    def test_before_day_is_midnight_but_old_date_end_includes_day(self):
        before = window(before="2026-11-04")
        legacy = window(date_end="2026-11-04")
        self.assertEqual(legacy["end_epoch"] - before["end_epoch"], 86400)

    def test_after_day_excludes_day_and_after_instant_is_strict(self):
        day = window(after="2026-11-04")
        self.assertEqual(day["start_utc"], "2026-11-05T00:00:00+00:00")
        self.assertTrue(day["start_inclusive"])
        compiled = search.compile_search_filter({"after": "1970-01-01T00:00:00Z", "before": "1970-01-02"})
        for epoch, matches in ((-1, False), (0, False), (.001, True), (86400, False)):
            self.assertEqual(search.match_search_filter({"created_at_epoch": epoch}, compiled) is not None, matches)

    def test_conflicting_bounds_anchors_and_periods_are_rejected(self):
        for values in ({"after": "2026-11-04", "date_start": "2026-11-04"},
                       {"before": "2026-11-04", "date_end": "2026-11-04"},
                       {"after": "2026-11-04", "before": "2026-11-05"},
                       {"date_period": "today", "date_start": "2026-11-04"},
                       {"date_anchor": "2026-11-04T12:00:00Z"},
                       {"date_period": "today", "date_anchor": "2026-11-04"},
                       {"date_period": "tomorrow"}, {"date_period": "last_month", "date_anchor": "0001-01-01T00:00:00Z"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                search.normalize_search_options(values)

    def test_relative_elapsed_periods_have_exact_duration_across_dst(self):
        for period, hours in (("last_24_hours", 24), ("last_7_days", 168), ("last_30_days", 720)):
            value = window(date_period=period, date_anchor="2026-11-02T00:00:00-08:00", timezone="America/Los_Angeles")
            self.assertEqual(value["end_epoch"] - value["start_epoch"], hours * 3600)

    def test_calendar_yesterday_observes_23_and_25_hour_days(self):
        for anchor, hours in (("2026-03-09T12:00:00-07:00", 23), ("2026-11-02T12:00:00-08:00", 25)):
            value = window(date_period="yesterday", date_anchor=anchor, timezone="America/Los_Angeles")
            self.assertEqual(value["end_epoch"] - value["start_epoch"], hours * 3600)

    def test_calendar_week_starts_monday_and_month_crosses_year(self):
        options = {"date_anchor": "2026-01-01T12:00:00Z"}
        expected = {"this_week": ("2025-12-29T00:00:00+00:00", "2026-01-01T12:00:00+00:00"),
                    "last_week": ("2025-12-22T00:00:00+00:00", "2025-12-29T00:00:00+00:00"),
                    "this_month": ("2026-01-01T00:00:00+00:00", "2026-01-01T12:00:00+00:00"),
                    "last_month": ("2025-12-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00")}
        for period, pair in expected.items():
            value = window(date_period=period, **options)
            self.assertEqual((value["start_utc"], value["end_utc"]), pair)
        leap = window(date_period="last_month", date_anchor="2024-03-15T00:00:00Z")
        self.assertEqual((leap["end_epoch"] - leap["start_epoch"]) / 86400, 29)

    def test_current_period_at_midnight_can_be_empty(self):
        compiled = search.compile_search_filter({"date_period": "today", "date_anchor": "2026-11-04T00:00:00Z"})
        self.assertEqual(compiled["start"], compiled["end"])
        self.assertIsNone(search.match_search_filter({"created_at_epoch": compiled["start"]}, compiled))

    def test_implicit_anchor_is_resolved_at_evaluation_not_normalization(self):
        options = search.normalize_search_options({"date_period": "last_24_hours"})
        self.assertEqual(options["date_anchor"], "")
        first = search.compile_search_filter(options, evaluation_epoch=86400)["dates"]
        second = search.compile_search_filter(options, evaluation_epoch=172800)["dates"]
        self.assertEqual((first["start_epoch"], first["end_epoch"]), (0, 86400))
        self.assertEqual((second["start_epoch"], second["end_epoch"]), (86400, 172800))
        frozen = search.compile_search_filter(dict(options, date_anchor=first["anchor_utc"]), evaluation_epoch=999999)["dates"]
        self.assertEqual(first, frozen)

    def test_dst_anchor_needs_offset_and_unknown_dates_do_not_match(self):
        options = {"date_period": "today", "timezone": "America/Los_Angeles"}
        for anchor in ("2026-03-08T02:30:00", "2026-11-01T01:30:00"):
            with self.assertRaises(ValueError):
                window(**options, date_anchor=anchor)
        compiled = search.compile_search_filter(dict(options, date_anchor="2026-11-01T01:30:00-07:00"))
        self.assertIsNone(search.match_search_filter({"timestamp": "unknown"}, compiled))

    def test_moving_relative_paging_and_feedback_require_anchor(self):
        for extra in ({"offset": 1, "sort": "newest"}, {"feedback_mode": "skip"}, {"feedback_action": "reset"}):
            with self.assertRaises(ValueError):
                search.normalize_search_options({"date_period": "last_7_days", **extra})
            search.normalize_search_options({"date_period": "last_7_days", "date_anchor": "2026-11-04T12:00:00Z", **extra})

    def test_feedback_does_not_cross_anchor_or_explicit_boundaries(self):
        ledger = search.SearchFeedbackLedger()
        request = search.normalize_search_options({"date_period": "last_7_days", "date_anchor": "2026-11-04T12:00:00Z", "feedback_mode": "skip"})
        plan = ledger.prepare(request)
        published = ledger.publish(plan, [])
        changed = dict(request, date_anchor="2026-11-05T12:00:00Z", feedback_action="reject_last", feedback_token=published["token"])
        with self.assertRaises(ValueError):
            ledger.prepare(changed)

    def test_named_options_preserve_new_fields_and_reject_duplicates(self):
        values = search.parse_search_options(["date_period=yesterday", 'date_anchor="2026-11-04T12:00:00Z"'], set(search.SEARCH_DEFAULTS))
        self.assertEqual(values["date_anchor"], "2026-11-04T12:00:00Z")
        self.assertTrue(search.search_has_filter(values))
        self.assertFalse(search.search_has_filter(search.normalize_search_options({})))
        with self.assertRaises(ValueError):
            search.parse_search_options(["after=2026-11-04", "after=2026-11-05"], set(search.SEARCH_DEFAULTS))


if __name__ == "__main__":
    unittest.main()
