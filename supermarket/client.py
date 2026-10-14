"""Authenticated, rate-limited Super Market API client."""
import os
import random
import sys
import time
from collections import deque

import requests


DEFAULT_BASE = os.environ.get("SUPERMARKET_BASE", "https://sig.thesuper.market/api/v1")
RETRYABLE_STATUS = {429, 503}


class ApiError(Exception):
    def __init__(self, resp):
        self.status = resp.status_code
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        self.code = err.get("code", "UNKNOWN")
        self.details = err.get("details")
        super().__init__(f"{self.status} {self.code}: {err.get('message', resp.text[:200])}")


class RateLimiter:
    """Sliding-window limiter: at most max_calls per period seconds."""

    def __init__(self, max_calls, period=60.0):
        self.max_calls, self.period = max_calls, period
        self.calls = deque()

    def wait(self):
        while True:
            now = time.monotonic()
            while self.calls and now - self.calls[0] >= self.period:
                self.calls.popleft()
            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                return
            time.sleep(self.period - (now - self.calls[0]) + 0.05)


class SuperMarketClient:
    def __init__(self, api_key, base=DEFAULT_BASE, reads_per_min=90):
        self.base = base.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
        self.reads = RateLimiter(reads_per_min)

    def get(self, path, params=None, max_retries=6):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        for attempt in range(max_retries):
            self.reads.wait()
            resp = self.session.get(self.base + path, params=params, timeout=30)
            if resp.status_code in RETRYABLE_STATUS:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2 ** attempt, 30)
                delay += random.uniform(0, 1)
                print(f"  {resp.status_code} on {path}; retrying in {delay:.1f}s", file=sys.stderr)
                time.sleep(delay)
                continue
            if not resp.ok:
                raise ApiError(resp)  # other 4xx/5xx won't be fixed by retrying
            return resp.json()
        raise ApiError(resp)

    def paginate(self, path, params=None, limit=100):
        cursor = None
        while True:
            page = self.get(path, {**(params or {}), "limit": limit, "cursor": cursor})
            rows = page.get("data", page if isinstance(page, list) else [])
            yield from rows
            pg = page.get("pagination") or {} if isinstance(page, dict) else {}
            if not pg.get("hasMore") or not pg.get("nextCursor"):
                return
            cursor = pg["nextCursor"]


