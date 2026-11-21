"""End-to-end setup test: config entry -> coordinator -> sensor registration."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

FIXTURE_BALANCE = {"currentBalance": 72.03, "lifetimeBalance": 292.03}

NOW = datetime.now(UTC)
FIXTURE_HISTORY = {
    (NOW - timedelta(minutes=15 * i)).isoformat().replace("+00:00", "Z"): 0.08
    for i in range(10)
}

FIXTURE_DEMAND = [
    {
        "demandTier": "high",
        "displayName": "NVIDIA RTX 5090",
        "earningRates": {"avgEarningRate": 0.32, "maxEarningRate": 0.48},
        "utilizationPct": 101,
    },
    {
        "demandTier": "low",
        "name": "Old GPU",
        "earningRates": {"avgEarningRate": 0.0},
        "utilizationPct": 0,
    },
]


async def test_setup_creates_sensors(hass, enable_custom_integrations):
    entry = MockConfigEntry(
        domain="salad_tracker",
        data={"token": "test-token"},
        options={"update_interval_min": 5, "enable_gpu_demand": True},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.salad_tracker.coordinator.SaladApiClient.async_get_balance",
            AsyncMock(return_value=FIXTURE_BALANCE),
        ),
        patch(
            "custom_components.salad_tracker.coordinator.SaladApiClient.async_get_earning_history",
            AsyncMock(return_value=FIXTURE_HISTORY),
        ),
        patch(
            "custom_components.salad_tracker.coordinator.SaladApiClient.async_get_gpu_demand",
            AsyncMock(return_value=FIXTURE_DEMAND),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    for eid in (
        "sensor.salad_balance",
        "sensor.salad_lifetime_balance",
        "sensor.salad_earnings_today",
        "sensor.salad_earnings_last_24_hours",
        "sensor.salad_earnings_last_7_days",
        "sensor.salad_earning_rate",
        "sensor.salad_last_earning",
        "sensor.salad_gpu_demand",
    ):
        state = hass.states.get(eid)
        assert state is not None, f"{eid} missing"
        print(f"{eid} = {state.state} ({state.attributes.get('unit_of_measurement')})")

    assert hass.states.get("sensor.salad_balance").state == "72.03"
    assert hass.states.get("sensor.salad_gpu_demand").state == "1"
