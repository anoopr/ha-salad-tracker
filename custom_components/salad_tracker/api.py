"""Salad app-api client and response parsing for the Salad Tracker integration.

Auth model (undocumented API, verified 2026-09/2026-11): requests carry the
`auth` cookie value from a logged-in app.salad.com session plus an
X-XSRF-TOKEN header whose value the server does not validate.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp

API_BASE = "https://app-api.salad.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# A 15-minute earning bucket is only considered "current" for this long after
# its timestamp; older newest-buckets mean reporting lag, so rate is unknown.
RATE_MAX_AGE = timedelta(minutes=45)
BUCKET_INTERVAL = timedelta(minutes=15)


class SaladApiClientError(Exception):
    """Base error for the Salad API client."""


class SaladApiAuthError(SaladApiClientError):
    """The auth cookie was rejected (HTTP 401/403)."""


class SaladApiConnectionError(SaladApiClientError):
    """Network/transport failure talking to the API."""


class SaladApiClient:
    """Minimal async client for Salad's undocumented app-api."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        """Store the session and auth cookie value."""
        self._session = session
        self._token = token

    async def _get(self, path: str) -> Any:
        """GET one API path and return decoded JSON."""
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            # The API rejects requests without this header (value unchecked).
            "X-XSRF-TOKEN": "salad-tracker",
            "Cookie": f"auth={self._token}",
        }
        try:
            async with asyncio.timeout(30):
                response = await self._session.get(
                    f"{API_BASE}{path}", headers=headers
                )
        except (TimeoutError, aiohttp.ClientError) as err:
            raise SaladApiConnectionError(
                f"Request to {path} failed: {err}"
            ) from err
        if response.status in (401, 403):
            response.release()
            raise SaladApiAuthError(
                f"Salad rejected the auth cookie (HTTP {response.status})"
            )
        if response.status >= 400:
            text = await response.text()
            response.release()
            raise SaladApiClientError(
                f"Salad API error HTTP {response.status} for {path}: {text[:200]}"
            )
        return await response.json(content_type=None)

    async def async_get_balance(self) -> Any:
        """Fetch /api/v1/profile/balance."""
        return await self._get("/api/v1/profile/balance")

    async def async_get_earning_history(self) -> Any:
        """Fetch /api/v2/reports/30-day-earning-history."""
        return await self._get("/api/v2/reports/30-day-earning-history")

    async def async_get_gpu_demand(self) -> Any:
        """Fetch /api/v2/demand-monitor/gpu."""
        return await self._get("/api/v2/demand-monitor/gpu")


def parse_balance(data: Any) -> tuple[float | None, float | None]:
    """Return (current, lifetime) balance, tolerating known shapes."""
    if not isinstance(data, dict):
        return None, None
    current = next(
        (float(data[k]) for k in ("currentBalance", "balance") if k in data),
        None,
    )
    lifetime = next(
        (float(data[k]) for k in ("lifetimeBalance", "lifetime") if k in data),
        None,
    )
    return current, lifetime


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO timestamp, defaulting naive values to UTC."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def parse_earning_buckets(data: Any) -> list[tuple[datetime, float]] | None:
    """Flatten the earning history into (timestamp, amount) buckets.

    Known shapes:
      * dict keyed by ISO timestamp -> 15-minute earning amount
      * dict with a list under data/earnings/history/items whose items carry
        date/day/endDate plus earning/amount/balanceChange/total/value keys

    Returns None when the shape is unrecognized so callers can distinguish
    "no earnings" from "cannot parse".
    """
    if not isinstance(data, dict):
        return None
    buckets: dict[str, float] = {}

    if data and all(
        isinstance(v, (int, float)) for v in data.values()
    ) and len(str(next(iter(data), ""))) >= 10:
        for ts, amount in data.items():
            buckets[str(ts)] = buckets.get(str(ts), 0.0) + float(amount)
    else:
        inner: Any = data
        for key in ("data", "earnings", "history", "items"):
            if isinstance(inner.get(key), list):
                inner = inner[key]
                break
        if not isinstance(inner, list):
            return None
        for item in inner:
            if not isinstance(item, dict):
                continue
            ts = item.get("date") or item.get("day") or item.get("endDate")
            amount = next(
                (
                    item[k]
                    for k in (
                        "earning",
                        "amount",
                        "balanceChange",
                        "total",
                        "value",
                    )
                    if k in item
                ),
                None,
            )
            if ts is None or amount is None:
                continue
            buckets[str(ts)] = buckets.get(str(ts), 0.0) + float(amount)

    parsed: list[tuple[datetime, float]] = []
    for ts, amount in buckets.items():
        stamp = _parse_timestamp(ts)
        if stamp is not None:
            parsed.append((stamp, amount))
    parsed.sort(key=lambda pair: pair[0])
    return parsed


def summarize(
    buckets: list[tuple[datetime, float]] | None,
    now: datetime,
    day_start,
) -> dict[str, Any]:
    """Aggregate 15-minute earning buckets.

    now: aware datetime for "current time"; day_start: callable returning the
    start of the local day for a given datetime. Rate is the newest bucket's
    value scaled to $/hour, or None when the newest bucket is stale.
    """
    result: dict[str, Any] = {
        "today": None,
        "last_24h": None,
        "last_7d": None,
        "rate": None,
        "last_bucket_at": None,
        "last_earning_at": None,
    }
    if not buckets:
        return result

    today_start = day_start(now)
    week_start = today_start - timedelta(days=6)
    window_start = now - timedelta(hours=24)

    today_values = [a for ts, a in buckets if ts >= today_start]
    window_values = [a for ts, a in buckets if ts >= window_start]
    week_values = [a for ts, a in buckets if ts >= week_start]

    if today_values:
        result["today"] = sum(today_values)
    if window_values:
        result["last_24h"] = sum(window_values)
    if week_values:
        result["last_7d"] = sum(week_values)

    newest_ts, newest_amount = buckets[-1]
    result["last_bucket_at"] = newest_ts
    for ts, amount in reversed(buckets):
        if amount > 0:
            result["last_earning_at"] = ts
            break
    if now - newest_ts <= RATE_MAX_AGE:
        result["rate"] = newest_amount * (timedelta(hours=1) / BUCKET_INTERVAL)
    return result


def parse_gpu_demand(data: Any) -> list[dict[str, Any]]:
    """Normalize the GPU demand-monitor list (tolerant of shape drift)."""
    if not isinstance(data, list):
        return []
    gpus: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rates = item.get("earningRates") or {}
        if not isinstance(rates, dict):
            rates = {}
        gpus.append(
            {
                "name": item.get("displayName") or item.get("name"),
                "tier": item.get("demandTier") or item.get("demandTierName"),
                "avg_rate": _num(rates.get("avgEarningRate")),
                "max_rate": _num(rates.get("maxEarningRate")),
                "utilization_pct": _num(item.get("utilizationPct")),
            }
        )
    return gpus


def _num(value: Any) -> float | None:
    """Return float(value) when numeric, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
