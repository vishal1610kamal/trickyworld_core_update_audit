"""Opt-in checks against the real services.

  LIVE=1 python3 -m unittest discover -s tests -p test_live.py      Google's public dashboard feed
  GSC_LIVE=1 GSC_PROPERTY=sc-domain:example.com GSC_SERVICE_ACCOUNT_FILE=key.json \
      python3 -m unittest discover -s tests -p test_live.py     your own Search Console property, read-only
"""
import datetime as dt
import os
import unittest

from fakes import ca


@unittest.skipUnless(os.environ.get("LIVE"), "set LIVE=1 to read Google's real dashboard feed")
class LiveDashboard(unittest.TestCase):
    def test_feed(self):
        found = ca.fetch_incidents(ca.DASHBOARD_FEED)
        cores = [i for i in found if i.is_core_update]
        self.assertTrue(cores, "no core update in the feed")
        for i in cores:
            self.assertTrue(i.begin.tzinfo and (i.end is None or i.end > i.begin))
        print("\n" + ca.status_text(ca.plan(cores[0], ca.today_pt(), found)))


@unittest.skipUnless(os.environ.get("GSC_LIVE") and os.environ.get("GSC_PROPERTY"),
                     "set GSC_LIVE=1 and GSC_PROPERTY to query your own property")
class LiveSearchConsole(unittest.TestCase):
    def test_read_only_queries(self):
        gsc = ca.SearchConsole.from_env()
        last = ca.last_final_day(gsc, ca.today_pt())
        self.assertIsNotNone(last, "no final data in the last 14 days")
        week = (last - dt.timedelta(days=6), last)
        total = gsc.query(week)
        pages = gsc.query(week, ["page"], max_rows=10)
        branded = gsc.query(week, filters=[("brandedClassification", "equals", "NON_BRANDED")])
        multimodal = gsc.query(week, type="webMultimodal")
        print(f"\nlast final day {last}; web clicks {total[0]['clicks'] if total else 0}; "
              f"top pages {len(pages)}; non-branded rows {len(branded)}; multimodal rows {len(multimodal)}")
        self.assertLessEqual(len(pages), 10)


if __name__ == "__main__":
    unittest.main()
