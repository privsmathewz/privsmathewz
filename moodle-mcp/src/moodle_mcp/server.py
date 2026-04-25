"""MCP server exposing Moodle to Claude Code.

Moodle auth modes:
- token: MOODLE_TOKEN — full Web Services access
- cookie: MOODLE_SESSION_COOKIE — page scraping + file downloads

Transport modes (set MCP_TRANSPORT):
- stdio (default) — local Claude Code usage
- sse — HTTP/SSE for remote deployments (Railway, Render, etc.)
  Listens on PORT (default 8000). Protect with MCP_API_KEY.
"""

from __future__ import annotations

import base64
import json
import os
import re
from html.parser import HTMLParser
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import MoodleClient, MoodleError

mcp = FastMCP("moodle")
_client: MoodleClient | None = None


def _c() -> MoodleClient:
    global _client
    if _client is None:
        _client = MoodleClient()
    return _client


def _ok(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _err(e: Exception) -> str:
    return json.dumps({"error": str(e)})


# ---------- Token-mode tools (Moodle Web Services) ----------


@mcp.tool()
async def whoami() -> str:
    """Return the Moodle site info and authenticated user. Token mode only."""
    try:
        return _ok(await _c().call("core_webservice_get_site_info"))
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def list_my_courses() -> str:
    """List courses you're enrolled in. Token mode only."""
    try:
        info = await _c().call("core_webservice_get_site_info")
        courses = await _c().call("core_enrol_get_users_courses", userid=info["userid"])
        return _ok(
            [
                {
                    "id": c["id"],
                    "shortname": c.get("shortname"),
                    "fullname": c.get("fullname"),
                    "visible": c.get("visible"),
                    "startdate": c.get("startdate"),
                    "enddate": c.get("enddate"),
                }
                for c in courses
            ]
        )
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def search_courses(query: str, page: int = 0, per_page: int = 20) -> str:
    """Search courses on the Moodle site by keyword. Token mode only."""
    try:
        return _ok(
            await _c().call(
                "core_course_search_courses",
                criterianame="search",
                criteriavalue=query,
                page=page,
                perpage=per_page,
            )
        )
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def get_course_contents(course_id: int) -> str:
    """Return the section/activity tree for a course. Token mode only."""
    try:
        return _ok(await _c().call("core_course_get_contents", courseid=course_id))
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def list_assignments(course_ids: list[int] | None = None) -> str:
    """List assignments across one or more courses. Token mode only."""
    try:
        params: dict[str, Any] = {}
        if course_ids:
            params["courseids"] = course_ids
        return _ok(await _c().call("mod_assign_get_assignments", **params))
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def get_assignment_submission_status(assignment_id: int) -> str:
    """Current submission status for an assignment. Token mode only."""
    try:
        return _ok(
            await _c().call("mod_assign_get_submission_status", assignid=assignment_id)
        )
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def upcoming_calendar() -> str:
    """Upcoming calendar events. Token mode only."""
    try:
        res = await _c().call(
            "core_calendar_get_action_events_by_timesort",
            limitnum=50,
            limittononsuspendedevents=1,
        )
        events = res.get("events", []) if isinstance(res, dict) else res
        return _ok(events)
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def list_forum_discussions(forum_id: int, page: int = 0, per_page: int = 20) -> str:
    """List discussions in a forum. Token mode only."""
    try:
        return _ok(
            await _c().call(
                "mod_forum_get_forum_discussions",
                forumid=forum_id,
                page=page,
                perpage=per_page,
            )
        )
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def get_grades(course_id: int) -> str:
    """Your grade items for a course. Token mode only."""
    try:
        info = await _c().call("core_webservice_get_site_info")
        return _ok(
            await _c().call(
                "gradereport_user_get_grade_items",
                courseid=course_id,
                userid=info["userid"],
            )
        )
    except MoodleError as e:
        return _err(e)


# ---------- Shared / cookie-mode tools ----------


@mcp.tool()
async def fetch_resource(file_url: str, max_text_chars: int = 20000) -> str:
    """Download an authenticated Moodle file URL (pluginfile.php, etc).

    Text-like content returns decoded text; binary returns base64 + metadata.
    Works in both token and cookie mode.
    """
    try:
        data, ctype = await _c().download(file_url)
        if _is_text(ctype):
            text = data.decode("utf-8", errors="replace")
            truncated = len(text) > max_text_chars
            return _ok(
                {
                    "content_type": ctype,
                    "bytes": len(data),
                    "truncated": truncated,
                    "text": text[:max_text_chars],
                }
            )
        return _ok(
            {
                "content_type": ctype,
                "bytes": len(data),
                "base64": base64.b64encode(data).decode("ascii"),
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool()
async def fetch_page(path_or_url: str, max_text_chars: int = 20000) -> str:
    """Fetch a Moodle HTML page, e.g. '/course/view.php?id=194996'.

    Accepts either a full URL or a site-relative path. Returns the raw HTML
    (truncated). Works in both auth modes and is the main tool for cookie mode.
    """
    try:
        html, ctype = await _c().fetch_page(path_or_url)
        truncated = len(html) > max_text_chars
        return _ok(
            {
                "content_type": ctype,
                "bytes": len(html),
                "truncated": truncated,
                "html": html[:max_text_chars],
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool()
async def get_course_html(course_id: int, include_resource_links: bool = True) -> str:
    """Fetch and lightly parse a course page. Returns:

    - title
    - visible text blocks (section headings + activity titles + intros)
    - resource/assignment links (mod/*, pluginfile.php)

    Works in both auth modes; useful when WS tools aren't available.
    """
    try:
        html, _ = await _c().fetch_page(f"/course/view.php?id={course_id}")
        parsed = _parse_course_html(html, base=_c().site)
        if not include_resource_links:
            parsed.pop("links", None)
        return _ok(parsed)
    except Exception as e:
        return _err(e)


# ---------- Helpers ----------


def _is_text(content_type: str) -> bool:
    ct = content_type.lower()
    return ct.startswith("text/") or "json" in ct or "xml" in ct


class _CourseParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.texts: list[str] = []
        self.links: list[dict[str, str]] = []
        self._in_title = False
        self._capture_text: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "a":
            href = a.get("href") or ""
            if any(k in href for k in ("/mod/", "pluginfile.php", "/course/view.php")):
                self._capture_text = []
                self.links.append({"href": href, "text": ""})
        elif tag in ("h1", "h2", "h3", "h4", "li", "p", "span") and a.get("class"):
            cls = a["class"] or ""
            if any(
                k in cls
                for k in ("sectionname", "instancename", "summary", "activityinstance")
            ):
                self._capture_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._capture_text is not None and self.links:
            text = "".join(self._capture_text).strip()
            self.links[-1]["text"] = text
            self._capture_text = None
        elif tag in ("h1", "h2", "h3", "h4", "li", "p", "span") and self._capture_text is not None:
            text = "".join(self._capture_text).strip()
            if text:
                self.texts.append(text)
            self._capture_text = None

    def handle_data(self, data: str) -> None:
        if self._in_title and not self.title:
            self.title = data.strip() or None
        if self._capture_text is not None:
            self._capture_text.append(data)


def _parse_course_html(html: str, base: str) -> dict[str, Any]:
    p = _CourseParser()
    p.feed(html)

    seen: set[str] = set()
    unique_text: list[str] = []
    for t in p.texts:
        cleaned = re.sub(r"\s+", " ", t).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique_text.append(cleaned)

    links_out: list[dict[str, str]] = []
    link_seen: set[str] = set()
    for link in p.links:
        href = link["href"]
        if href.startswith("/"):
            href = base + href
        key = href
        if key in link_seen:
            continue
        link_seen.add(key)
        links_out.append({"text": link["text"], "href": href})

    return {"title": p.title, "text_blocks": unique_text, "links": links_out}


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport == "sse":
        _run_sse()
    else:
        mcp.run()



def _run_sse() -> None:
    """Run the MCP server over HTTP/SSE for remote deployments."""
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse
    from starlette.routing import Mount, Route

    port = int(os.environ.get("PORT", "8000"))

    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp._mcp_server.run(
                streams[0],
                streams[1],
                mcp._mcp_server.create_initialization_options(),
            )

    async def health(_: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages", app=sse_transport.handle_post_message),
            Route("/health", endpoint=health),
        ]
    )

    print(f"moodle-mcp SSE server starting on port {port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
