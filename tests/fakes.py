"""
Test helpers. The two fixtures are real files saved on 17 November 2026: Google's Search Status Dashboard feed and the
Search Console API's discovery document (revision 20261115). Search Console itself is replaced by FakeSearchConsole,
which aggregates synthetic rows the way the API documents: grouped by the requested dimensions, filtered, sorted by
clicks, paged with rowLimit and startRow, and with anonymized queries (query=None) counted in page and site totals
but never returned as query rows. None of the traffic numbers in these tests come from a real site.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import coreaudit as ca  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")
INCIDENTS = os.path.join(FIXTURES, "incidents-2026-11-17.json")
DISCOVERY = os.path.join(FIXTURES, "searchconsole-v1-discovery-20261115.json")
SITE = "sc-domain:example.com"


def incidents() -> list[ca.Incident]:
    return ca.fetch_incidents(INCIDENTS)


class Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code, self._payload, self.text = status_code, payload, json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class FakeSearchConsole:
    """A requests-like session that answers Search Analytics and URL Inspection calls from `facts`."""

    FILTER_FIELDS = {"page": "page", "query": "query", "brandedClassification": "branded",
                     "country": "country", "device": "device"}

    def __init__(self, facts: list[dict], windows: dict[str, str], final_through: dt.date,
                 status_code: int = 200, error: str = ""):
        self.facts, self.windows, self.final_through = facts, windows, final_through
        self.status_code, self.error = status_code, error
        self.bodies: list[tuple[str, dict]] = []

    def post(self, url: str, json: dict | None = None, timeout: float | None = None) -> Response:
        body = json or {}
        self.bodies.append((url, body))
        if self.status_code != 200:
            return Response(self.status_code, {"error": {"code": self.status_code, "message": self.error}})
        if url == ca.INSPECT_API:
            return Response(200, {"inspectionResult": {"indexStatusResult": {
                "verdict": "NEUTRAL", "coverageState": "Crawled - currently not indexed",
                "lastCrawlTime": "2026-06-05T10:00:00Z", "googleCanonical": body["inspectionUrl"]}}})
        dims = body.get("dimensions", [])
        start, end = dt.date.fromisoformat(body["startDate"]), dt.date.fromisoformat(body["endDate"])
        if dims == ["date"]:
            last = min(end, self.final_through)
            rows = [{"keys": [(start + dt.timedelta(days=i)).isoformat()], "clicks": 1, "impressions": 10,
                     "ctr": 0.1, "position": 5.0} for i in range((last - start).days + 1)]
            return Response(200, {"rows": rows} if rows else {})
        label = self.windows.get(body["startDate"])
        facts = [f for f in self.facts if f["window"] == label and f.get("type", "web") == body.get("type", "web")]
        for group in body.get("dimensionFilterGroups", []):
            for flt in group.get("filters", []):
                field = self.FILTER_FIELDS[flt["dimension"]]
                facts = [f for f in facts if f.get(field) == flt["expression"]]
        if "query" in dims:
            facts = [f for f in facts if f.get("query")]
        groups: dict[tuple, list[float]] = {}
        for f in facts:
            g = groups.setdefault(tuple(f[d] for d in dims), [0, 0, 0])
            g[0] += f["clicks"]
            g[1] += f["impressions"]
            g[2] += f.get("position", 0) * f["impressions"]
        rows = [{"keys": list(k), "clicks": c, "impressions": i, "ctr": c / i if i else 0,
                 "position": p / i if i else 0} for k, (c, i, p) in groups.items()]
        rows.sort(key=lambda r: -r["clicks"])
        start_row, limit = body.get("startRow", 0), body.get("rowLimit", 1000)
        page = rows[start_row:start_row + limit]
        return Response(200, {"rows": page, "responseAggregationType": "byPage"} if page else
                        {"responseAggregationType": "byPage"})


U = "https://example.com"


def fact(window: str, page: str, query: str | None, clicks: float, impressions: float, position: float,
         branded: str | None = "NON_BRANDED", type: str = "web") -> dict:
    return {"window": window, "page": U + page, "query": query, "clicks": clicks, "impressions": impressions,
            "position": position, "branded": branded, "type": type}


def may_2026_site() -> list[dict]:
    """A made-up site around the May 2026 core update (before 14-20 May, after 3-9 June 2026)."""
    rows = []
    for w, a in (("before", False), ("after", True)):
        rows += [
            # /guides/alpha/: its main query falls from 4 to 29 (Google's large-drop example)...
            fact(w, "/guides/alpha/", "alpha guide", *((20, 600, 29) if a else (200, 2000, 4))),
            # ...a second query keeps its place but is clicked less...
            fact(w, "/guides/alpha/", "alpha tutorial", *((50, 1000, 3.1) if a else (80, 1000, 3.0))),
            # ...and some clicks come from anonymized queries the API never lists
            fact(w, "/guides/alpha/", None, *((10, 400, 8) if a else (30, 500, 6))),
            # /guides/beta/: 2 to 4, Google's small-drop example
            fact(w, "/guides/beta/", "beta setup", *((70, 2500, 4) if a else (100, 2500, 2))),
            # /news/gamma/: same position, fewer searches
            fact(w, "/news/gamma/", "gamma news", *((30, 600, 5.2) if a else (50, 1000, 5))),
            # the brand query doesn't move
            fact(w, "/about/", "example brand", 40, 100, 1, branded="BRANDED"),
            # /blog/epsilon/ gains
            fact(w, "/blog/epsilon/", "epsilon tips", *((60, 900, 6) if a else (20, 500, 9))),
            # other search types
            fact(w, "/guides/alpha/", None, *((4, 280, 13) if a else (5, 300, 12)), type="image"),
            fact(w, "/news/gamma/", None, *((5, 300, 0) if a else (25, 900, 0)), type="discover"),
        ]
        if not a:   # /guides/delta/ disappears from the results
            rows.append(fact(w, "/guides/delta/", "delta errors", 30, 400, 7))
    rows += [fact("ly_before", "/guides/alpha/", None, 500, 9000, 6), fact("ly_after", "/guides/alpha/", None, 450, 9000, 6)]
    return rows


MAY_WINDOWS = {"2026-05-14": "before", "2026-06-03": "after", "2025-05-15": "ly_before", "2025-06-04": "ly_after"}


def may_client(**kw) -> tuple[ca.SearchConsole, FakeSearchConsole]:
    session = FakeSearchConsole(kw.pop("facts", None) or may_2026_site(), MAY_WINDOWS,
                                kw.pop("final_through", dt.date(2026, 6, 14)), **kw)
    return ca.SearchConsole(SITE, session), session


def may_plan(today: dt.date = dt.date(2026, 6, 15)) -> ca.Plan:
    found = incidents()
    return ca.plan(ca.find_update(found, "may 2026"), today, found)
