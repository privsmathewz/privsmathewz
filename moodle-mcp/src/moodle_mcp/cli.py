"""Standalone CLI: print enrolled Moodle courses to stdout."""

from __future__ import annotations

import asyncio
import json
import sys

from .client import MoodleClient, MoodleError


async def _list() -> None:
    try:
        c = MoodleClient()
    except MoodleError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        info = await c.call("core_webservice_get_site_info")
        courses = await c.call("core_enrol_get_users_courses", userid=info["userid"])
    except MoodleError as e:
        print(f"Moodle error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await c.aclose()

    rows = [
        {
            "id": course["id"],
            "shortname": course.get("shortname"),
            "fullname": course.get("fullname"),
            "visible": course.get("visible"),
            "startdate": course.get("startdate"),
            "enddate": course.get("enddate"),
        }
        for course in courses
    ]

    if not rows:
        print("No courses found.")
        return

    # Human-readable table
    col_w = max(len(r["shortname"] or "") for r in rows)
    print(f"{'ID':<8}  {'Short name':<{col_w}}  Full name")
    print("-" * (8 + 2 + col_w + 2 + 40))
    for r in rows:
        print(f"{r['id']:<8}  {(r['shortname'] or ''):<{col_w}}  {r['fullname'] or ''}")

    print()
    print(json.dumps(rows, indent=2, default=str))


def main() -> None:
    asyncio.run(_list())
