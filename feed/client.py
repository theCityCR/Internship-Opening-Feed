"""String Web Access client: every network read in this project goes through here.

* Counts each billed attempt against a hard budget (default 150).
* Caches responses on disk (keyed by method+url+body) so re-runs and tests cost nothing.
  Cache hits are counted separately and are NOT String requests.
* Read-only by design: POST is allowed only because some job boards (Workday) use POST
  for *searching*; nothing is ever submitted, applied to, or logged into.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx

FETCH_URL = "https://request.usestring.ai/v1/fetch"


class BudgetExceeded(RuntimeError):
    pass


class FetchError(RuntimeError):
    pass


class StringClient:
    def __init__(self, api_key: str, cache_dir: str | Path | None = ".cache/string",
                 max_requests: int = 150, timeout: float = 90.0):
        self.api_key = api_key
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_requests = max_requests
        self.requests_made = 0      # billed attempts sent to String
        self.cache_hits = 0
        self.by_type: dict[str, int] = {}   # x-billed-request-type -> count
        self._http = httpx.Client(timeout=timeout)
        self._lock = threading.Lock()

    # ---- cache -------------------------------------------------------------
    @staticmethod
    def _key(method: str, url: str, body: Any) -> str:
        raw = json.dumps([method.upper(), url, body], sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _cache_path(self, key: str) -> Path | None:
        return self.cache_dir / f"{key}.json" if self.cache_dir else None

    # ---- fetch -------------------------------------------------------------
    def fetch(self, url: str, method: str = "GET", body: Any = None,
              headers: dict[str, str] | None = None, use_cache: bool = True) -> Any:
        """Return the destination's parsed body (dict/list for JSON, str otherwise)."""
        key = self._key(method, url, body)
        cp = self._cache_path(key)
        if use_cache and cp and cp.is_file():
            with self._lock:
                self.cache_hits += 1
            return json.loads(cp.read_text())["data"]

        payload: dict[str, Any] = {"url": url, "format": "json"}
        if method.upper() != "GET":
            payload["method"] = method.upper()
        if body is not None:
            payload["body"] = body
        if headers or body is not None:
            payload["headers"] = {"Content-Type": "application/json", **(headers or {})}

        last_err = ""
        for attempt in range(3):
            with self._lock:
                if self.requests_made >= self.max_requests:
                    raise BudgetExceeded(f"String request budget of {self.max_requests} reached")
                self.requests_made += 1
            try:
                r = self._http.post(FETCH_URL, json=payload,
                                    headers={"Authorization": f"Bearer {self.api_key}"})
            except httpx.HTTPError as e:
                last_err = f"network error: {e}"
                time.sleep(1.5 * (attempt + 1))
                continue
            billed = r.headers.get("x-billed-request-type")
            if billed:
                with self._lock:
                    self.by_type[billed] = self.by_type.get(billed, 0) + 1
            if r.status_code in (429, 502, 503, 504):
                last_err = f"String API {r.status_code}"
                time.sleep(2.0 * (attempt + 1))
                continue
            if r.status_code != 200:
                raise FetchError(f"String API {r.status_code} for {url}: {r.text[:200]}")
            env = r.json()
            status = env.get("statusCode")
            if status != 200:
                raise FetchError(f"Destination returned {status} for {url}")
            if cp:
                cp.write_text(json.dumps({"url": url, "method": method, "data": env.get("data")}))
            return env.get("data")
        raise FetchError(f"Giving up on {url}: {last_err}")

    def stats(self) -> dict[str, Any]:
        return {"string_requests": self.requests_made, "budget": self.max_requests,
                "cache_hits": self.cache_hits, "by_type": dict(self.by_type)}
