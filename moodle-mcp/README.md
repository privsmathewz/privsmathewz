# moodle-mcp

An MCP (Model Context Protocol) server that lets Claude Code read your Moodle
courses, assignments, deadlines, grades, forum posts, and resource files
through the official Moodle Web Services API.

Built for `moodle.mmu.ac.uk` but works with any Moodle site that has Web
Services enabled.

## Two auth modes

**Token mode (preferred).** Set `MOODLE_TOKEN`. All Web Services tools work.

**Cookie mode (fallback).** Set `MOODLE_SESSION_COOKIE` (the `MoodleSession`
cookie from a logged-in browser). Page-scrape tools work; Web Services tools
do not. Use this when your institution doesn't expose a student token.

## What Claude can do once it's wired up

Token-mode tools:

- `whoami` — confirm the site and logged-in user
- `list_my_courses` — every course you're enrolled in
- `search_courses` — keyword search across the site
- `get_course_contents` — full section/activity tree for a course (incl. file URLs)
- `list_assignments` — assignments across one or all courses
- `get_assignment_submission_status` — your current submission state
- `upcoming_calendar` — upcoming deadlines and events
- `list_forum_discussions` — forum thread listing
- `get_grades` — your grade items for a course

Shared tools (work in both modes):

- `fetch_page` — fetch any Moodle HTML page (e.g. `/course/view.php?id=194996`)
- `get_course_html` — fetch + lightly parse a course page into title / text
  blocks / resource links
- `fetch_resource` — download an authenticated file URL; returns text for
  text/JSON/XML, base64 otherwise

## 1. Get a Moodle Web Services token

1. Log in at https://moodle.mmu.ac.uk.
2. Click your avatar → **Preferences** → under *User account* click
   **Security keys**.
3. Copy the token for **Moodle mobile web service** (if visible).

If no token is shown, Web Services for students may be disabled at MMU — ask
the e-learning team to enable `moodle_mobile_app` for your account, or use the
session-cookie fallback (see bottom of this file).

## 2. Install the server

Requires Python 3.10+.

```bash
cd moodle-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 3. Configure credentials

Pick **one** auth mode and export it:

```bash
# Token mode (preferred)
export MOODLE_SITE_URL="https://moodle.mmu.ac.uk"
export MOODLE_TOKEN="paste-your-token-here"

# --- OR ---

# Cookie mode (fallback)
export MOODLE_SITE_URL="https://moodle.mmu.ac.uk"
export MOODLE_SESSION_COOKIE="paste-MoodleSession-value-here"
```

Cookie-mode tip: log in on a laptop, F12 → **Application** → **Cookies** →
`https://moodle.mmu.ac.uk` → copy the `MoodleSession` value. The cookie
expires on logout or after a few hours of inactivity — re-grab it when Claude
reports a login redirect.

Sanity check:

```bash
MOODLE_SITE_URL=... MOODLE_TOKEN=... python -c "
import asyncio
from moodle_mcp.client import MoodleClient
async def main():
    c = MoodleClient()
    print(await c.call('core_webservice_get_site_info'))
    await c.aclose()
asyncio.run(main())
"
```

## 4. Register with Claude Code

From anywhere, run:

Token mode:

```bash
claude mcp add moodle \
  --env MOODLE_SITE_URL=https://moodle.mmu.ac.uk \
  --env MOODLE_TOKEN=YOUR_TOKEN \
  -- /absolute/path/to/moodle-mcp/.venv/bin/moodle-mcp
```

Cookie mode:

```bash
claude mcp add moodle \
  --env MOODLE_SITE_URL=https://moodle.mmu.ac.uk \
  --env MOODLE_SESSION_COOKIE=YOUR_MOODLESESSION_VALUE \
  -- /absolute/path/to/moodle-mcp/.venv/bin/moodle-mcp
```

Then in a new Claude Code session:

```
/mcp
```

`moodle` should be listed as connected. Try:

> List my Moodle courses, then show me the contents of course 194996.

Claude will call `list_my_courses` and `get_course_contents` automatically.

## 5. Deploy to Railway (access from anywhere)

Deploy once to Railway and Claude Code on any device — phone, laptop, uni PC
— connects to the same running server without local Python installs.

### One-time setup

1. Create a free account at [railway.app](https://railway.app).
2. Install the Railway CLI: `npm i -g @railway/cli` (or use the dashboard).
3. From the `moodle-mcp/` directory:

```bash
railway login
railway init          # creates a new project
railway up            # builds + deploys using the Dockerfile
```

4. In the Railway dashboard → your service → **Variables**, add:

| Variable | Value |
|---|---|
| `MOODLE_SITE_URL` | `https://moodle.mmu.ac.uk` |
| `MOODLE_TOKEN` | your WS token — **or** — |
| `MOODLE_SESSION_COOKIE` | your MoodleSession cookie value |
| `MCP_API_KEY` | a long random string you make up (protects the endpoint) |

5. In **Settings → Networking**, click **Generate Domain** to get a public URL
   like `https://moodle-mcp-production.up.railway.app`.

### Connect Claude Code to the remote server

Run this once on each device (phone, laptop, etc.) — no Python install needed:

```bash
claude mcp add moodle \
  --transport sse \
  --header "Authorization: Bearer YOUR_MCP_API_KEY" \
  https://moodle-mcp-production.up.railway.app/sse
```

Then just ask Claude: *"Get the contents of my Moodle course 194996."*

### Refreshing the session cookie

The `MoodleSession` cookie expires every few hours. When Claude reports a
login redirect, grab a fresh cookie (F12 → Application → Cookies) and update
the Railway variable — the server restarts in seconds.

## Security

- Never commit `MOODLE_TOKEN` or `MOODLE_SESSION_COOKIE` — they're full
  account credentials. `.env` is gitignored for this reason.
- Set `MCP_API_KEY` on Railway so only you can reach your deployed server.
- A session cookie grants the same access as being logged in in the browser;
  rotate it by logging out if a value leaks.
- The server makes requests only to `MOODLE_SITE_URL` — no third-party calls.

## Layout

```
moodle-mcp/
├── Dockerfile          # container for Railway / any Docker host
├── railway.toml        # Railway build + deploy config
├── pyproject.toml
├── README.md
└── src/moodle_mcp/
    ├── __init__.py
    ├── client.py       # async Moodle WS REST client (token + cookie modes)
    └── server.py       # FastMCP server + tools (stdio + SSE transports)
```

## License

MIT.
