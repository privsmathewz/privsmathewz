"""Async Moodle client supporting two auth modes.

Token mode (preferred)
    Set MOODLE_SITE_URL and MOODLE_TOKEN. All Web Services REST calls work,
    plus authenticated pluginfile downloads via ?token=.

Cookie mode (fallback, for sites that don't expose a token to students)
    Set MOODLE_SITE_URL and MOODLE_SESSION_COOKIE. The MoodleSession cookie
    is attached to every request. WS calls are not guaranteed to work in
    this mode, but regular Moodle pages and pluginfile.php downloads do.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class MoodleError(RuntimeError):
    pass


class MoodleClient:
    def __init__(
        self,
        site_url: str | None = None,
        token: str | None = None,
        session_cookie: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        site = (site_url or os.environ.get("MOODLE_SITE_URL", "")).rstrip("/")
        tok = token or os.environ.get("MOODLE_TOKEN", "") or None
        cookie = session_cookie or os.environ.get("MOODLE_SESSION_COOKIE", "") or None
        if not site:
            raise MoodleError("MOODLE_SITE_URL must be set (e.g. https://moodle.mmu.ac.uk).")
        if not tok and not cookie:
            raise MoodleError(
                "Set MOODLE_TOKEN (Web Services token) or MOODLE_SESSION_COOKIE "
                "(MoodleSession cookie value)."
            )
        self._site = site
        self._token = tok
        self._cookie = cookie
        cookies = {"MoodleSession": cookie} if cookie else None
        self._http = httpx.AsyncClient(
            timeout=timeout,
            cookies=cookies,
            follow_redirects=True,
            headers={"User-Agent": "moodle-mcp/0.1 (+https://github.com/privsmathewz)"},
        )

    @property
    def site(self) -> str:
        return self._site

    @property
    def has_token(self) -> bool:
        return self._token is not None

    @property
    def has_cookie(self) -> bool:
        return self._cookie is not None

    async def aclose(self) -> None:
        await self._http.aclose()

    async def call(self, wsfunction: str, **params: Any) -> Any:
        """Invoke a Moodle Web Service function. Requires token mode."""
        if not self._token:
            raise MoodleError(
                f"'{wsfunction}' needs a Web Services token (MOODLE_TOKEN). "
                "In cookie mode, use fetch_page / get_course_html instead."
            )
        url = f"{self._site}/webservice/rest/server.php"
        data: dict[str, str] = {
            "wstoken": self._token,
            "wsfunction": wsfunction,
            "moodlewsrestformat": "json",
        }
        _flatten(data, params)
        r = await self._http.post(url, data=data)
        r.raise_for_status()
        payload = r.json()
        if isinstance(payload, dict) and payload.get("exception"):
            raise MoodleError(
                f"{payload.get('errorcode', 'error')}: {payload.get('message', 'unknown')}"
            )
        return payload

    async def download(self, file_url: str) -> tuple[bytes, str]:
        """Download an authenticated Moodle file URL.

        Token mode appends ?token=. Cookie mode relies on the attached
        MoodleSession cookie.
        """
        url = file_url
        if self._token:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}token={self._token}"
        r = await self._http.get(url)
        r.raise_for_status()
        return r.content, r.headers.get("content-type", "application/octet-stream")

    async def fetch_page(self, path_or_url: str) -> tuple[str, str]:
        """Fetch a Moodle HTML page. Accepts a full URL or a path like
        '/course/view.php?id=194996'. Works in either auth mode (cookie mode
        is the usual reason to use it)."""
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            if not path_or_url.startswith("/"):
                path_or_url = "/" + path_or_url
            url = f"{self._site}{path_or_url}"
        r = await self._http.get(url)
        r.raise_for_status()
        if _looks_like_login(r.text):
            raise MoodleError(
                "Moodle returned the login page — your session cookie is "
                "missing, expired, or the URL requires a different login."
            )
        return r.text, r.headers.get("content-type", "text/html")


def _looks_like_login(html: str) -> bool:
    lowered = html.lower()
    return (
        "login/index.php" in lowered
        and ("username" in lowered and "password" in lowered)
    )


def _flatten(out: dict[str, str], value: Any, prefix: str = "") -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            key = f"{prefix}[{k}]" if prefix else str(k)
            _flatten(out, v, key)
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            key = f"{prefix}[{i}]" if prefix else str(i)
            _flatten(out, v, key)
    elif value is None:
        return
    elif isinstance(value, bool):
        out[prefix] = "1" if value else "0"
    else:
        out[prefix] = str(value)
