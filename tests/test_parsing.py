"""Tests for the pure parsing/aggregation helpers (no Home Assistant needed)."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "custom_components" / "salad_tracker")
)

from api import (  # noqa: E402
    parse_balance,
    parse_earning_buckets,
    parse_gpu_demand,
    summarize,
)


def ts(day, hour=0, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def day_start(dt):
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def test_parse_balance_current_shape():
    assert parse_balance({"currentBalance": 12.5, "lifetimeBalance": 900.0}) == (
        12.5,
        900.0,
    )


def test_parse_earning_buckets_dict_shape():
    data = {
        "2026-11-20T08:15:00Z": 0.08,
        "2026-11-20T08:00:00Z": 0.08,
        "2026-11-19T07:00:00Z": 0.32,
    }
    buckets = parse_earning_buckets(data)
    assert buckets is not None
    assert [t for t, _ in buckets] == [
        ts(19, 7, 0),
        ts(20, 8, 0),
        ts(20, 8, 15),
    ]


def test_parse_earning_buckets_wrapped_list_shape():
    data = {
        "data": [
            {"date": "2026-11-19", "earning": 0.32},
            {"day": "2026-11-20", "amount": 0.16},
        ]
    }
    buckets = parse_earning_buckets(data)
    assert buckets is not None
    assert len(buckets) == 2


def test_parse_earning_buckets_unknown_shape():
    assert parse_earning_buckets({"foo": "bar"}) is None
    assert parse_earning_buckets([1, 2, 3]) is None
    assert parse_earning_buckets(None) is None


def test_summarize_windows():
    now = ts(20, 12, 0)
    buckets = [
        (ts(13, 23, 45), 1.0),
        (ts(19, 7, 0), 0.32),      # 7 days ago
        (ts(20, 11, 30), 0.04),
        (ts(20, 11, 45), 0.08),    # newest
    ]
    s = summarize(buckets, now, day_start)
    assert s["today"] == 0.12
    assert s["last_24h"] == 0.12
    assert s["last_7d"] == 0.44
    assert s["rate"] == 0.32  # newest bucket 0.08 * 4
    assert s["last_earning_at"] == ts(20, 11, 45)
    assert s["last_bucket_at"] == ts(20, 11, 45)


def test_summarize_stale_rate_is_none():
    now = ts(20, 12, 0)
    buckets = [(ts(20, 11, 0), 0.08)]  # 60 minutes old > 45 min window
    s = summarize(buckets, now, day_start)
    assert s["rate"] is None
    assert s["last_earning_at"] == ts(20, 11, 0)


def test_summarize_no_buckets_today_is_none_not_zero():
    now = ts(20, 0, 30)
    buckets = [(ts(19, 23, 0), 0.08)]
    s = summarize(buckets, now, day_start)
    assert s["today"] is None
    assert s["last_24h"] == 0.08


def test_parse_gpu_demand():
    data = [
        {
            "demandTier": "high",
            "displayName": "NVIDIA RTX 5090",
            "earningRates": {"avgEarningRate": 0.32, "maxEarningRate": 0.48},
            "utilizationPct": 101,
        },
        {"demandTier": "low", "name": "Old GPU", "utilizationPct": 0},
        {"nonsense": True},
    ]
    gpus = parse_gpu_demand(data)
    assert len(gpus) == 3
    assert gpus[0]["tier"] == "high"
    assert gpus[0]["name"] == "NVIDIA RTX 5090"
    assert gpus[0]["avg_rate"] == 0.32
    assert gpus[1]["avg_rate"] is None
    assert gpus[2]["name"] is None
