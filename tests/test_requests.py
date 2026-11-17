"""Every request the client sends, checked against Google's discovery document for the Search Console API
(revision 20261115, saved 17 November 2026): field names, enum values, paths, methods and OAuth scopes."""
import datetime as dt
import json
import unittest
from urllib.parse import unquote

from fakes import DISCOVERY, SITE, FakeSearchConsole, ca, may_client, may_plan

W = (dt.date(2026, 5, 14), dt.date(2026, 5, 20))


def norm(value: str) -> str:
    # the reference pages write values as "webMultimodal" or "notContains"; the discovery enums as
    # WEB_MULTIMODAL and NOT_CONTAINS. The API reads them case-insensitively.
    return value.replace("_", "").lower()


class AgainstDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(DISCOVERY, encoding="utf-8") as f:
            cls.doc = json.load(f)
        cls.schemas = cls.doc["schemas"]
        res = cls.doc["resources"]
        cls.query_method = res["searchanalytics"]["methods"]["query"]
        cls.inspect_method = res["urlInspection"]["resources"]["index"]["methods"]["inspect"]

    def enum(self, schema: str, prop: str) -> set[str]:
        p = self.schemas[schema]["properties"][prop]
        return {norm(v) for v in (p.get("enum") or p["items"]["enum"])}

    def bodies(self) -> list[tuple[str, dict]]:
        gsc, session = may_client()
        gsc.query(W, type="webMultimodal")
        gsc.query(W, ["page", "query"], filters=[("page", "equals", "https://example.com/a/"),
                                                 ("query", "notContains", "brand")])
        gsc.query(W, filters=[("brandedClassification", "equals", "NON_BRANDED")])
        gsc.inspect("https://example.com/a/")
        ca.audit(gsc, may_plan(), yoy=True, inspect=2)
        return session.bodies

    def test_paths_methods_and_scope(self):
        root = self.doc["rootUrl"] + self.doc.get("servicePath", "")
        self.assertEqual(ca.QUERY_API, root + self.query_method["path"].replace("{siteUrl}", "{site}"))
        self.assertEqual(ca.INSPECT_API, root + self.inspect_method["path"])
        self.assertEqual((self.query_method["httpMethod"], self.inspect_method["httpMethod"]), ("POST", "POST"))
        self.assertIn(ca.SCOPE, self.query_method["scopes"])
        self.assertIn(ca.SCOPE, self.inspect_method["scopes"])
        self.assertTrue(ca.SCOPE.endswith(".readonly"))

    def test_every_body_uses_documented_fields_and_values(self):
        request = self.schemas["SearchAnalyticsQueryRequest"]["properties"]
        checked = 0
        for url, body in self.bodies():
            if url == ca.INSPECT_API:
                self.assertLessEqual(set(body), set(self.schemas["InspectUrlIndexRequest"]["properties"]))
                continue
            self.assertEqual(unquote(url.split("/sites/")[1].split("/")[0]), SITE)
            self.assertLessEqual(set(body), set(request), body)
            self.assertNotIn("searchType", body)                     # deprecated: "use type instead"
            self.assertIn(norm(body["type"]), self.enum("SearchAnalyticsQueryRequest", "type"))
            self.assertIn(norm(body["dataState"]), self.enum("SearchAnalyticsQueryRequest", "dataState"))
            self.assertTrue(1 <= body["rowLimit"] <= 25000 and body["startRow"] >= 0)
            for d in body.get("dimensions", []):
                self.assertIn(norm(d), self.enum("SearchAnalyticsQueryRequest", "dimensions"))
            for group in body.get("dimensionFilterGroups", []):
                self.assertLessEqual(set(group), set(self.schemas["ApiDimensionFilterGroup"]["properties"]))
                self.assertIn(norm(group["groupType"]), self.enum("ApiDimensionFilterGroup", "groupType"))
                for f in group["filters"]:
                    self.assertLessEqual(set(f), set(self.schemas["ApiDimensionFilter"]["properties"]))
                    self.assertIn(norm(f["dimension"]), self.enum("ApiDimensionFilter", "dimension"))
                    self.assertIn(norm(f["operator"]), self.enum("ApiDimensionFilter", "operator"))
            checked += 1
        self.assertGreater(checked, 30)

    def test_every_search_type_we_query_exists(self):
        types = self.enum("SearchAnalyticsQueryRequest", "type")
        self.assertEqual({norm(t) for t in ca.SEARCH_TYPES} - types, set())


class Paging(unittest.TestCase):
    def test_pages_of_25000(self):
        many = [{"window": "before", "page": f"https://example.com/p{i}/", "query": None, "clicks": 1,
                 "impressions": 10, "position": 5, "type": "web"} for i in range(25003)]
        session = FakeSearchConsole(many, {"2026-05-14": "before"}, dt.date(2026, 6, 14))
        rows = ca.SearchConsole(SITE, session).query(W, ["page"])
        self.assertEqual(len(rows), 25003)
        self.assertEqual([b["startRow"] for _, b in session.bodies], [0, 25000])
        capped = ca.SearchConsole(SITE, FakeSearchConsole(many, {"2026-05-14": "before"}, dt.date(2026, 6, 14)))
        self.assertEqual(len(capped.query(W, ["page"], max_rows=100)), 100)

    def test_errors_explain_themselves(self):
        gsc, _ = may_client(status_code=403, error="User does not have sufficient permission for site")
        with self.assertRaises(ca.AuditError) as e:
            gsc.query(W)
        self.assertIn("403", str(e.exception))
        self.assertIn("user of this property", str(e.exception))


if __name__ == "__main__":
    unittest.main()
