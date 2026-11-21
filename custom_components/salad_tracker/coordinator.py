"""Data update coordinator for the Salad Tracker integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    ConfigEntryAuthFailed,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import (
    SaladApiClient,
    SaladApiAuthError,
    SaladApiClientError,
    parse_balance,
    parse_earning_buckets,
    parse_gpu_demand,
    summarize,
)
from .const import (
    CONF_ENABLE_GPU_DEMAND,
    CONF_UPDATE_INTERVAL_MIN,
    DEFAULT_ENABLE_GPU_DEMAND,
    DEFAULT_UPDATE_INTERVAL_MIN,
    DOMAIN,
    LOGGER,
)


@dataclass
class SaladUpdateData:
    """Data gathered by the coordinator."""

    balance: float | None = None
    lifetime_balance: float | None = None
    earnings_today: float | None = None
    earnings_24h: float | None = None
    earnings_7d: float | None = None
    rate: float | None = None
    last_bucket_at: datetime | None = None
    last_earning_at: datetime | None = None
    gpu_demand: list[dict[str, Any]] = field(default_factory=list)
    history_ok: bool = False


class SaladDataUpdateCoordinator(DataUpdateCoordinator[SaladUpdateData]):
    """Poll Salad's app-api for balance, earnings, and GPU demand."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator from a config entry."""
        interval_min = entry.options.get(
            CONF_UPDATE_INTERVAL_MIN, DEFAULT_UPDATE_INTERVAL_MIN
        )
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval_min),
        )
        self.client = SaladApiClient(
            async_get_clientsession(hass), entry.data["token"]
        )
        self.enable_gpu_demand = entry.options.get(
            CONF_ENABLE_GPU_DEMAND, DEFAULT_ENABLE_GPU_DEMAND
        )

    async def _async_update_data(self) -> SaladUpdateData:
        """Fetch all endpoints in parallel and aggregate."""
        fetches = [
            self.client.async_get_balance(),
            self.client.async_get_earning_history(),
        ]
        if self.enable_gpu_demand:
            fetches.append(self.client.async_get_gpu_demand())

        try:
            results = await asyncio.gather(*fetches)
        except SaladApiAuthError as err:
            raise ConfigEntryAuthFailed(
                "Salad auth cookie expired or invalid"
            ) from err
        except SaladApiClientError as err:
            raise UpdateFailed(f"Error fetching Salad data: {err}") from err
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timed out fetching Salad data: {err}") from err

        data = SaladUpdateData()

        current, lifetime = parse_balance(results[0])
        if current is None:
            raise UpdateFailed("Unrecognized balance response shape")
        data.balance = current
        data.lifetime_balance = lifetime

        buckets = parse_earning_buckets(results[1])
        if buckets is None:
            LOGGER.warning("Unrecognized earning-history shape; earnings unknown")
        else:
            data.history_ok = True
            summary = summarize(
                buckets,
                dt_util.now(),
                lambda dt: dt_util.start_of_local_day(dt),
            )
            data.earnings_today = summary["today"]
            data.earnings_24h = summary["last_24h"]
            data.earnings_7d = summary["last_7d"]
            data.rate = summary["rate"]
            data.last_bucket_at = summary["last_bucket_at"]
            data.last_earning_at = summary["last_earning_at"]

        if self.enable_gpu_demand and len(results) > 2:
            data.gpu_demand = parse_gpu_demand(results[2])

        return data
