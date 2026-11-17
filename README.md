# coreaudit: check a Google core update against your Search Console data

A command-line tool and a read-only MCP server that compare your Search Console data around a Google core update
the way Google's own guide says to, so an AI agent (Claude Code, Antigravity, Cursor) can do the legwork without
guessing.

Google's page [Google Search's core updates and your website](https://developers.google.com/search/docs/appearance/core-updates)
(last updated 10 December 2025) gives the steps:

1. Confirm on the Search Status Dashboard that the update has finished rolling out.
2. Wait at least a full week after it completes, then compare that week with the week before it started.
3. Review top pages and queries. A small drop in position (2 to 4) needs no drastic action; a large one (4 to 29)
   needs a deeper assessment.
4. Analyse each search type separately.

`coreaudit` reads the dates from the dashboard's public feed, refuses to compare until Google's waiting period is
over, then pulls the two weeks from the Search Console API with a read-only scope and sorts every change into the
patterns of Google's [Debugging drops in Google Search traffic](https://developers.google.com/search/docs/monitor-debug/debugging-search-traffic-drops)
guide. It changes nothing and decides nothing.

This is the code from the TrickyWorld article
[November 2026 core update: an agentic SEO audit](https://www.trickyworld.in/artificial-intelligence-machine-learning/ai-agents/november-2026-core-update-agentic-seo-audit/).

Python 3.10 or newer. Tested on 3.10, 3.11 and 3.12, with the MCP Python SDK 2.2.0 and 2.3.0.

## Commands

```bash
python3 coreaudit.py status                 # the latest core update: dates, the weeks to compare, caveats
python3 coreaudit.py status --all           # every core update in Google's feed
python3 coreaudit.py audit --site sc-domain:example.com --yoy --inspect 5
python3 coreaudit.py compare --site sc-domain:example.com --before 2026-11-03 --after 2026-12-01
```

`status` needs nothing but Python: no packages, no credentials. On 17 November 2026 it printed:

```
November 2026 core update
  started   10 Nov 2026 10:06 PT (18:06 UTC)
  status    still rolling out: Google hasn't marked it complete
  before    3 to 9 Nov 2026 (the week before it started)
  after     the 7 days after Google marks it complete
  overlaps  none
  source    https://status.search.google.com/incidents/WLxcJyC6jMWMfryxsKMc
```

It also flags weeks that are hard to compare. For the March 2026 core update, the week before it started included
the March 2026 spam update (24 to 25 March). Both of that update's weeks also fall between 13 May 2025 and 27 April
2026, when, according to Google's [Data anomalies page](https://support.google.com/webmasters/answer/6211453),
Search Console misreported impressions (clicks were not affected).

`audit` answers "not yet" without credentials until Google marks the update complete and the week after it has
final data. `--force` compares the latest finished week anyway and labels the result preliminary. When it runs, it
reports:

- **Each search type separately:** web, image, video, news, Discover, Google News and web multimodal (Lens, Circle
  to Search and image uploads). Discover and Google News have no position.
- **Branded vs non-branded** web clicks, using the `brandedClassification` filter Google added to the API on
  16 November 2026. It only works for eligible properties (top-level, with enough queries); others get no rows,
  and the report says so.
- **Where the loss is:** one page, a group of pages (a URL section), or site-wide.
- **The pages that lost the most clicks**, each with its change split by the pattern of the queries behind it. What
  the listed queries don't explain (anonymized queries, rows the API drops) is reported as *unattributed*.
- **Queries by pattern**, with what Google says about each.
- `--yoy`: the same weeks a year earlier (web clicks only), to spot seasonality.
- `--inspect N`: URL Inspection for up to N pages that vanished or fell far (2,000 inspections a day per property).
- **What it couldn't check**, for a person to look at.

Here is the text report for the made-up site in the test suite (none of these numbers come from a real site):

```
May 2026 core update: ready
Weeks compared: 2026-05-14 to 2026-05-20 (before) vs 2026-06-03 to 2026-06-09 (after)

By search type (clicks; impressions; position):
  web            550 → 280 (-49.1%); 8,000 → 6,100; 3.9 → 6.9
  image          5 → 4 (-20.0%); 300 → 280; 12.0 → 13.0
  discover       25 → 5 (-80.0%); 900 → 300

Branded vs non-branded (web clicks):
  branded        40 → 40 (0.0%)
  non-branded    510 → 240 (-52.9%)

Where: one page: https://example.com/guides/alpha/ lost 74% of the clicks lost

Pages that lost the most clicks:
  https://example.com/guides/alpha/
    clicks 310 → 80, position 4.0 → 11.8: large drop in position -180, fewer clicks, position held -30,
    unattributed (anonymized or unlisted queries) -20
```

Look at that first page. Averaged over its queries, it only slipped from 4.0 to 11.8, which reads as a small drop.
Split by query, one query fell from 4 to 29, Google's own example of a large drop, and cost 180 of the 230 clicks.
Page-level averages hide that, which is why the tool explains each page through its queries.

## The patterns

| Pattern | This tool's rule (defaults) | What Google's guides say |
|---|---|---|
| `large_drop` | 10+ places worse, or from the top 10 to below 20 | "Large drop in position (dropping from position 4 to 29): Do a deeper assessment." |
| `small_drop` | 1 to 10 places worse | "Small drop in position (dropping from position 2 to 4): There's no need to take drastic action" |
| `fewer_clicks_not_rank` | position held or improved; clicks down 20% (and 5+), mostly from a lower CTR | "If your impressions remain the same but your clicks drop, you might not be generating the best page title and snippet [...] or perhaps other sites had a more appealing rich result." |
| `less_demand` | position held; clicks down mostly from fewer impressions, or impressions down 20% | "Seasonality and changing interests": check Google Trends and 16 months of data |
| `vanished` | impressions before, none after | Check indexing (technical issues) with URL Inspection |
| `gain`, `steady`, `new`, `too_little_data` | the rest; under 50 before-week impressions is too little to judge | |

Clicks are impressions times CTR, so a click change splits exactly into a part from fewer impressions and a part
from a lower CTR. The bigger part names the pattern. Google gives examples, not numbers, so the thresholds are this
tool's reading of them: change them with `--min-impressions` and `--large-position`, or `Thresholds` in code.

A better position with fewer clicks counts as `fewer_clicks_not_rank`, not a gain: Google's
[performance data help](https://support.google.com/webmasters/answer/7042828) says "An AI Overview occupies a single
position in search results, and all links in the AI Overview are assigned that same position."

## Install and credentials

```bash
git clone https://github.com/vishal1610kamal/trickyworld_core_update_audit.git
cd trickyworld_core_update_audit
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

The tool only ever requests `https://www.googleapis.com/auth/webmasters.readonly`. Search Console's write methods
(submitting or deleting sitemaps, adding or deleting properties) need the full `webmasters` scope, which it never
asks for. Two ways to sign in:

**A service account** (best for a server or a scheduled job). In Google Cloud, enable the Google Search Console API,
create a service account and a JSON key. In Search Console, open Settings, then Users and permissions, and add the
service account's e-mail with **Restricted** permission. Then:

```bash
export GSC_SERVICE_ACCOUNT_FILE=/home/you/keys/gsc-reader.json   # outside the repo, chmod 600
export GSC_PROPERTY=sc-domain:example.com                         # or https://www.example.com/
```

**Your own Google account** (Application Default Credentials). gcloud requires the cloud-platform scope alongside
the one you need:

```bash
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/webmasters.readonly,https://www.googleapis.com/auth/cloud-platform
gcloud auth application-default set-quota-project YOUR_PROJECT_ID   # a project with the Search Console API enabled
export GSC_PROPERTY=sc-domain:example.com
```

## As an MCP server

`mcp_server.py` exposes three tools, all marked `readOnlyHint`:

| Tool | What it does |
|---|---|
| `core_update_status` | Google's dates for an update and the two weeks to compare. No credentials needed. |
| `core_update_audit` | The comparison. Answers "not yet", without touching credentials, until Google's waiting period is over. |
| `compare_weeks` | The same comparison for any two windows of 1 to 28 days. |

The property comes from `GSC_PROPERTY`, not from the agent, so a prompt can't point the tools at another site the
credentials can read. Errors (a bad date, an unknown update, a refused API call) go back to the agent as readable
messages.

**Claude Code:**

```bash
claude mcp add core-update-audit --scope user \
  -e GSC_PROPERTY=sc-domain:example.com \
  -e GSC_SERVICE_ACCOUNT_FILE=/home/you/keys/gsc-reader.json \
  -- /path/to/trickyworld_core_update_audit/.venv/bin/python /path/to/trickyworld_core_update_audit/mcp_server.py
```

**Antigravity CLI and IDE** (`~/.gemini/config/mcp_config.json`, the path Google's Analytics MCP guide gives) and
**Cursor** (`.cursor/mcp.json`) take the same entry: see [examples/mcp_config.json](examples/mcp_config.json).

Pair it with Google's official [Analytics MCP server](https://developers.google.com/analytics/devguides/MCP)
(`analytics-mcp`) to see what the lost visits were worth: GA4 has key events, but no search queries or positions.
[examples/core-update-audit.md](examples/core-update-audit.md) is a prompt that uses both. With Claude Code it can
run unattended, limited to the read tools:

```bash
claude -p "$(cat examples/core-update-audit.md)" \
  --permission-mode dontAsk \
  --allowedTools "mcp__core-update-audit__core_update_status mcp__core-update-audit__core_update_audit mcp__analytics-mcp__run_report" \
  > "reports/core-update-$(date +%F).md"
```

## What it can't see

- **Manual actions and security issues.** Google's traffic-drop guide lists both as causes, and the Search Console
  API has no endpoint for either. Check those reports by hand.
- **Anonymized queries.** Google: "Anonymized queries are those that aren't issued by more than a few dozen users
  over a two-to-three month period." They count in page and site totals but never appear as rows, hence
  *unattributed*.
- **Every row.** The API returns top rows, up to 50,000 per day per search type, sorted by clicks, and this tool
  reads at most 50,000 rows per query.
- **The generative AI performance report** (impressions in AI Overviews and AI Mode). It is in Search Console only;
  its data is already part of the web totals.
- **Search Console's own glitches.** Check the Data anomalies page for your two weeks. For example, a logging error
  cut impressions in the generative AI report from 9 to 11 November 2026, the days around the November 2026 core
  update's start.

## Tests

```bash
python3 -m unittest discover -s tests              # Python 3.10+: the MCP tests are skipped without the SDK
LIVE=1 python3 -m unittest discover -s tests -p test_live.py      # Google's real dashboard feed
GSC_LIVE=1 GSC_PROPERTY=... GSC_SERVICE_ACCOUNT_FILE=... python3 -m unittest discover -s tests -p test_live.py
```

- The dashboard tests use Google's real feed, saved on 17 November 2026 (`tests/fixtures/`). Rollout lengths match
  the dashboard's history page to the hour.
- Every request the client sends is checked against Google's discovery document for the Search Console API
  (revision 20261115, saved the same day): field names, enum values, paths, HTTP methods and the scope.
- Search Console itself is replaced by a stand-in that aggregates made-up rows the way the API documents. The MCP
  server is tested through the official SDK's client, in-process and as a real stdio subprocess.
- **Not tested here: a live Search Console property.** The opt-in `GSC_LIVE` test runs five read-only queries against
  yours.
