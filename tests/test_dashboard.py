"""Google's Search Status Dashboard feed (the real one, saved 17 November 2026) and the weeks it implies."""
import datetime as dt
import unittest

from fakes import ca, incidents

D = dt.date


class DashboardFeed(unittest.TestCase):
    def setUp(self):
        self.incidents = incidents()

    def test_core_updates_in_the_feed(self):
        names = [i.name for i in self.incidents if i.is_core_update]
        self.assertEqual(names, ["November 2026 core update", "May 2026 core update", "March 2026 core update",
                                 "December 2025 core update"])
        # the Discover update and the spam updates are ranking incidents, but not core updates
        self.assertIn("February 2026 Discover update", [i.name for i in self.incidents])

    def test_find_update(self):
        self.assertEqual(ca.find_update(self.incidents).name, "November 2026 core update")
        self.assertEqual(ca.find_update(self.incidents, "MAY 2026").name, "May 2026 core update")
        with self.assertRaises(ca.AuditError):
            ca.find_update(self.incidents, "june 2025")

    def test_rollout_lengths_match_the_dashboard(self):
        # the dashboard's history page: May 2026 "11 days, 21 hours", March 2026 "12 days, 4 hours",
        # December 2025 "18 days, 2 hours" (rounded)
        hours = {i.name: (i.end - i.begin).total_seconds() / 3600 for i in self.incidents if i.is_core_update and i.end}
        self.assertEqual(hours["May 2026 core update"], 11 * 24 + 21)
        self.assertEqual(hours["March 2026 core update"], 12 * 24 + 4)
        self.assertAlmostEqual(hours["December 2025 core update"], 18 * 24 + 2, delta=0.5)

    def test_november_2026_is_still_rolling_out(self):
        nov = ca.find_update(self.incidents, "november 2026")
        p = ca.plan(nov, D(2026, 11, 17), self.incidents)
        self.assertFalse(nov.complete)
        self.assertEqual(nov.first_day(), D(2026, 11, 10))      # 10:06 PST
        self.assertEqual((p.status, p.before, p.after, p.ready_on), ("rolling_out", (D(2026, 11, 3), D(2026, 11, 9)), None, None))
        self.assertEqual(p.warnings, [])                         # nothing else happened 3-9 November

    def test_may_2026_waiting_then_ready(self):
        may = ca.find_update(self.incidents, "may 2026")
        self.assertEqual((may.first_day(), may.last_day()), (D(2026, 5, 21), D(2026, 6, 2)))
        waiting = ca.plan(may, D(2026, 6, 11), self.incidents)
        self.assertEqual((waiting.status, waiting.after, waiting.ready_on),
                         ("waiting", (D(2026, 6, 3), D(2026, 6, 9)), D(2026, 6, 12)))
        self.assertEqual(ca.plan(may, D(2026, 6, 12), self.incidents).status, "ready")

    def test_march_2026_before_week_overlaps_the_spam_update(self):
        p = ca.plan(ca.find_update(self.incidents, "march 2026"), D(2026, 11, 17), self.incidents)
        self.assertEqual(p.before, (D(2026, 3, 20), D(2026, 3, 26)))   # 02:00 PDT on 27 March: DST already on
        self.assertTrue(any("March 2026 spam update (24 to 25 Mar 2026)" in w for w in p.warnings), p.warnings)
        self.assertIn("The before and after weeks fall between 13 May 2025 and 27 April 2026", " ".join(p.warnings))

    def test_december_2025_after_week_is_new_year(self):
        p = ca.plan(ca.find_update(self.incidents, "december 2025"), D(2026, 11, 17), self.incidents)
        self.assertEqual(p.after, (D(2025, 12, 30), D(2026, 1, 5)))
        self.assertTrue(any("oldest incident" in w for w in p.warnings))

    def test_pacific_time_decides_the_day(self):
        late = ca.Incident("x core update", "Ranking", ca._timestamp("2026-11-10T07:30:00Z"), None)
        self.assertEqual(late.first_day(), D(2026, 11, 9))       # 23:30 PST on the 9th
        summer = ca.Incident("x core update", "Ranking", ca._timestamp("2026-06-01T06:30:00+00:00"), None)
        self.assertEqual(summer.first_day(), D(2026, 5, 31))     # 23:30 PDT

    def test_status_text(self):
        text = ca.status_text(ca.plan(ca.find_update(self.incidents), D(2026, 11, 17), self.incidents))
        self.assertIn("started   10 Nov 2026 10:06 PT (18:06 UTC)", text)
        self.assertIn("before    3 to 9 Nov 2026", text)
        self.assertIn("still rolling out", text)

    def test_cli_status_offline(self):
        import contextlib, io, os
        os.environ["COREAUDIT_INCIDENTS"] = os.path.join(os.path.dirname(__file__), "fixtures", "incidents-2026-11-17.json")
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ca.main(["status", "--all", "--today", "2026-11-17"])
            self.assertEqual(code, 0)
            self.assertEqual(out.getvalue().count("core update\n"), 4)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):   # "not yet" needs no credentials
                code = ca.main(["audit", "--today", "2026-11-17"])
            self.assertEqual(code, 0)
            self.assertIn("hasn't marked the November 2026 core update complete", out.getvalue())
        finally:
            del os.environ["COREAUDIT_INCIDENTS"]


if __name__ == "__main__":
    unittest.main()
