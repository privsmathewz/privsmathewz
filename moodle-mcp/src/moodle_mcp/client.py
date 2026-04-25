"""Thin async wrapper around the Moodle Web Services REST API."""

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
        timeout: float = 30.0,
    ) -> None:
        site = (site_url or os.environ.get("MOODLE_SITE_URL", "")).rstrip("/")
        tok = token or os.environ.get("MOODLE_TOKEN", "")
        if not site or not tok:
            raise MoodleError(
                "MOODLE_SITE_URL and MOODLE_TOKEN must be set "
                "(e.g. https://moodle.mmu.ac.uk and your Web Services token)."
            )
        self._site = site
        self._token = tok
        self._http = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def call(self, wsfunction: str, **params: Any) -> Any:
        """Invoke a Moodle Web Service function.

        Array parameters in Moodle WS use PHP-style bracket notation, e.g.
        ``courseids[0]=1&courseids[1]=2``. This helper flattens lists/dicts
        into that form.
        """
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
        """Download a pluginfile URL, appending the token. Returns (bytes, content_type)."""
        sep = "&" if "?" in file_url else "?"
        url = f"{file_url}{sep}token={self._token}"
        r = await self._http.get(url, follow_redirects=True)
        r.raise_for_status()
        return r.content, r.headers.get("content-type", "application/octet-stream")


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
