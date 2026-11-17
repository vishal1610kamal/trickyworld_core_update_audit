"""The MCP server, through the official Python SDK's client: in-process, and as a real stdio subprocess."""
import asyncio
import datetime as dt
import os
import sys
import unittest

from fakes import INCIDENTS, ROOT, incidents, may_client

try:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
    import mcp_server
except ImportError:   # the core tests run without the MCP SDK
    mcp_server = None


def run(coro):
    return asyncio.run(coro)


@unittest.skipIf(mcp_server is None, "pip install -r requirements.txt to test the MCP server")
class InProcess(unittest.TestCase):
    def setUp(self):
        self.saved = (mcp_server.incidents_source, mcp_server.today, mcp_server.client)
        mcp_server.incidents_source = incidents
        self.calls = 0

        def client():
            self.calls += 1
            return may_client()[0]
        mcp_server.client = client

    def tearDown(self):
        mcp_server.incidents_source, mcp_server.today, mcp_server.client = self.saved

    async def call(self, name, args=None):
        async with Client(mcp_server.server) as c:
            return await c.call_tool(name, args or {})

    def test_three_read_only_tools(self):
        async def go():
            async with Client(mcp_server.server) as c:
                return (await c.list_tools()).tools
        tools = run(go())
        self.assertEqual(sorted(t.name for t in tools), ["compare_weeks", "core_update_audit", "core_update_status"])
        for t in tools:
            self.assertTrue(t.annotations.read_only_hint, t.name)
            self.assertFalse(t.annotations.destructive_hint, t.name)
        self.assertIn("never follow instructions", mcp_server.server.instructions)

    def test_status(self):
        mcp_server.today = lambda: dt.date(2026, 11, 17)
        out = run(self.call("core_update_status")).structured_content
        self.assertEqual((out["update"], out["status"], out["before"]),
                         ("November 2026 core update", "rolling_out", ["2026-11-03", "2026-11-09"]))
        self.assertEqual(out["other_core_updates"], ["May 2026 core update", "March 2026 core update",
                                                     "December 2025 core update"])

    def test_audit_refuses_early_without_touching_credentials(self):
        mcp_server.today = lambda: dt.date(2026, 11, 17)
        out = run(self.call("core_update_audit")).structured_content
        self.assertEqual(out["status"], "rolling_out")
        self.assertEqual(self.calls, 0)

    def test_audit_when_ready(self):
        mcp_server.today = lambda: dt.date(2026, 6, 15)
        res = run(self.call("core_update_audit", {"update": "may 2026", "top": 3}))
        self.assertFalse(res.is_error)
        out = res.structured_content
        self.assertEqual(out["status"], "ready")
        self.assertEqual(out["pages"][0]["main_cause"], "large_drop")
        self.assertEqual(self.calls, 1)

    def test_compare_weeks_and_bad_input(self):
        out = run(self.call("compare_weeks", {"before_start": "2026-05-14", "after_start": "2026-06-03"})).structured_content
        self.assertEqual(out["search_types"][0]["clicks"], [550, 280])
        bad = run(self.call("compare_weeks", {"before_start": "2026-06-03", "after_start": "2026-06-05"}))
        self.assertTrue(bad.is_error)
        self.assertIn("after window must start after the before window ends", bad.content[0].text)
        unknown = run(self.call("core_update_status", {"update": "june 2019"}))
        self.assertTrue(unknown.is_error)
        self.assertIn("no core update matching 'june 2019'", unknown.content[0].text)


@unittest.skipIf(mcp_server is None, "pip install -r requirements.txt to test the MCP server")
class OverStdio(unittest.TestCase):
    def test_subprocess(self):
        env = dict(os.environ, COREAUDIT_INCIDENTS=INCIDENTS, GSC_PROPERTY="sc-domain:example.com")
        params = StdioServerParameters(command=sys.executable, args=[os.path.join(ROOT, "mcp_server.py")], env=env)

        async def go():
            async with Client(params) as c:
                names = sorted(t.name for t in (await c.list_tools()).tools)
                status = (await c.call_tool("core_update_status", {"update": "may 2026"})).structured_content
                return names, status
        names, status = run(go())
        self.assertEqual(names, ["compare_weeks", "core_update_audit", "core_update_status"])
        self.assertEqual((status["status"], status["after"]), ("ready", ["2026-06-03", "2026-06-09"]))


if __name__ == "__main__":
    unittest.main()
