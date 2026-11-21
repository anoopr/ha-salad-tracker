"""Sensor platform for the Salad Tracker integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import SaladDataUpdateCoordinator, SaladUpdateData


@dataclass(frozen=True, kw_only=True)
class SaladSensorEntityDescription(SensorEntityDescription):
    """Sensor description that knows how to read the coordinator data."""

    value_fn: Callable[[SaladUpdateData], Any]


SENSORS: tuple[SaladSensorEntityDescription, ...] = (
    SaladSensorEntityDescription(
        key="balance",
        translation_key="balance",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: data.balance,
    ),
    SaladSensorEntityDescription(
        key="lifetime_balance",
        translation_key="lifetime_balance",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: data.lifetime_balance,
    ),
    SaladSensorEntityDescription(
        key="earnings_today",
        translation_key="earnings_today",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=3,
        value_fn=lambda data: data.earnings_today,
    ),
    SaladSensorEntityDescription(
        key="earnings_24h",
        translation_key="earnings_24h",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=3,
        value_fn=lambda data: data.earnings_24h,
    ),
    SaladSensorEntityDescription(
        key="earnings_7d",
        translation_key="earnings_7d",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=3,
        value_fn=lambda data: data.earnings_7d,
    ),
    SaladSensorEntityDescription(
        key="earning_rate",
        translation_key="earning_rate",
        native_unit_of_measurement="$/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:speedometer",
        value_fn=lambda data: data.rate,
    ),
    SaladSensorEntityDescription(
        key="last_earning",
        translation_key="last_earning",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        value_fn=lambda data: data.last_earning_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Salad Tracker sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        SaladSensor(coordinator, description) for description in SENSORS
    ]
    if coordinator.enable_gpu_demand:
        entities.append(SaladGpuDemandSensor(coordinator))
    async_add_entities(entities)


def _device_info(entry_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="Salad",
        manufacturer="Salad",
        model="SaladChef (app-api.salad.com)",
    )


class SaladSensor(
    CoordinatorEntity[SaladDataUpdateCoordinator], SensorEntity
):
    """One Salad metric backed by the coordinator."""

    entity_description: SaladSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SaladDataUpdateCoordinator,
        description: SaladSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}::{description.key}"
        )
        self._attr_device_info = _device_info(coordinator.config_entry.entry_id)

    @property
    def native_value(self) -> Any:
        """Return the current value from coordinator data."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attach sync metadata."""
        attributes: dict[str, Any] = {}
        synced = self.coordinator.last_success_time
        if synced is not None:
            attributes["last_synced"] = dt_util.as_local(synced).isoformat()
        data = self.coordinator.data
        if data.last_bucket_at is not None:
            attributes["last_observation"] = data.last_bucket_at.isoformat()
        return attributes


class SaladGpuDemandSensor(
    CoordinatorEntity[SaladDataUpdateCoordinator], SensorEntity
):
    """GPU demand snapshot from Salad's demand monitor."""

    _attr_has_entity_name = True
    _attr_translation_key = "gpu_demand"
    _attr_icon = "mdi:expansion-card"

    def __init__(self, coordinator: SaladDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}::gpu_demand"
        )
        self._attr_device_info = _device_info(coordinator.config_entry.entry_id)

    @property
    def native_value(self) -> int | None:
        """Return the number of GPUs currently in high demand."""
        gpus = self.coordinator.data.gpu_demand
        if not gpus:
            return None
        return sum(1 for gpu in gpus if gpu.get("tier") == "high")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose per-GPU demand detail."""
        gpus = self.coordinator.data.gpu_demand
        if not gpus:
            return {}
        counts: dict[str, int] = {}
        for gpu in gpus:
            tier = str(gpu.get("tier") or "unknown")
            counts[tier] = counts.get(tier, 0) + 1
        top = sorted(
            gpus, key=lambda gpu: gpu.get("avg_rate") or 0.0, reverse=True
        )[:8]
        return {
            "total_gpus": len(gpus),
            "demand_counts": counts,
            "top_by_avg_rate": [
                "{} ({}): avg ${:.3f}/h, util {:.0f}%".format(
                    gpu.get("name"),
                    gpu.get("tier") or "?",
                    gpu.get("avg_rate") or 0.0,
                    gpu.get("utilization_pct") or 0.0,
                )
                for gpu in top
            ],
        }
