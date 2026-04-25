"""MCP server exposing Moodle Web Services as tools."""

from __future__ import annotations

import base64
import json
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


@mcp.tool()
async def whoami() -> str:
    """Return the current Moodle site info and the authenticated user."""
    try:
        info = await _c().call("core_webservice_get_site_info")
        return _ok(info)
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def list_my_courses() -> str:
    """List courses the authenticated user is enrolled in."""
    try:
        info = await _c().call("core_webservice_get_site_info")
        user_id = info["userid"]
        courses = await _c().call("core_enrol_get_users_courses", userid=user_id)
        summary = [
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
        return _ok(summary)
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def search_courses(query: str, page: int = 0, per_page: int = 20) -> str:
    """Search courses on the Moodle site by keyword."""
    try:
        res = await _c().call(
            "core_course_search_courses",
            criterianame="search",
            criteriavalue=query,
            page=page,
            perpage=per_page,
        )
        return _ok(res)
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def get_course_contents(course_id: int) -> str:
    """Return the full section/activity tree for a course, including resource URLs."""
    try:
        sections = await _c().call("core_course_get_contents", courseid=course_id)
        return _ok(sections)
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def list_assignments(course_ids: list[int] | None = None) -> str:
    """List assignments across one or more courses. Omit course_ids for all enrolled courses."""
    try:
        params: dict[str, Any] = {}
        if course_ids:
            params["courseids"] = course_ids
        res = await _c().call("mod_assign_get_assignments", **params)
        return _ok(res)
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def get_assignment_submission_status(assignment_id: int) -> str:
    """Return the current submission status for an assignment (the authenticated user)."""
    try:
        res = await _c().call(
            "mod_assign_get_submission_status", assignid=assignment_id
        )
        return _ok(res)
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def upcoming_calendar(days: int = 30) -> str:
    """Upcoming calendar events (deadlines, lectures) for the next N days."""
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
    """List discussions in a forum activity."""
    try:
        res = await _c().call(
            "mod_forum_get_forum_discussions",
            forumid=forum_id,
            page=page,
            perpage=per_page,
        )
        return _ok(res)
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def get_grades(course_id: int) -> str:
    """Return the authenticated user's grade items for a course."""
    try:
        info = await _c().call("core_webservice_get_site_info")
        user_id = info["userid"]
        res = await _c().call(
            "gradereport_user_get_grade_items", courseid=course_id, userid=user_id
        )
        return _ok(res)
    except MoodleError as e:
        return _err(e)


@mcp.tool()
async def fetch_resource(file_url: str, max_text_chars: int = 20000) -> str:
    """Download a Moodle pluginfile URL. Returns decoded text for text-like content,
    otherwise returns base64 with metadata. Pass a URL from ``get_course_contents``."""
    try:
        data, ctype = await _c().download(file_url)
        if ctype.startswith("text/") or "json" in ctype or "xml" in ctype:
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
