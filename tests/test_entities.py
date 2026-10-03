"""Tests for the Clue sensors and binary sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.clue.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import FROZEN_TIME, build_calendar
from datetime import date


def _state(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.unique_id}_{key}"
    )
    assert entity_id is not None, key
    return hass.states.get(entity_id)


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant, mock_clue_client: MagicMock, config_entry: MockConfigEntry
) -> MockConfigEntry:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.mark.freeze_time(FROZEN_TIME)
async def test_sensor_states(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    expected = {
        "cycle_day": "20",
        "phase": "luteal",
        "next_period": "2025-05-30",
        "days_until_next_period": "9",
        "last_period_start": "2025-05-02",
        "last_period_length": "4",
        "next_ovulation": "2025-06-13",
    }
    for key, value in expected.items():
        assert _state(hass, loaded_entry, "sensor", key).state == value, key


@pytest.mark.freeze_time(FROZEN_TIME)
async def test_phase_sensor_is_enum(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    state = _state(hass, loaded_entry, "sensor", "phase")
    assert state.attributes["device_class"] == "enum"
    assert "luteal" in state.attributes["options"]


@pytest.mark.freeze_time(FROZEN_TIME)
async def test_binary_sensor_states(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    assert _state(hass, loaded_entry, "binary_sensor", "period").state == STATE_OFF
    assert _state(hass, loaded_entry, "binary_sensor", "ovulation_day").state == STATE_OFF

    fertile = _state(hass, loaded_entry, "binary_sensor", "fertile_window")
    assert fertile.state == STATE_OFF
    # Today is past this cycle's window, so the next one is reported.
    assert str(fertile.attributes["window_start"]) == "2025-06-08"
    assert str(fertile.attributes["window_end"]) == "2025-06-14"


@pytest.mark.freeze_time("2025-05-04 12:00:00-03:00")
async def test_states_during_period(
    hass: HomeAssistant,
    mock_clue_client: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    mock_clue_client.get_connection_calendar.return_value = build_calendar(
        today=date(2025, 5, 21)
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert _state(hass, config_entry, "binary_sensor", "period").state == STATE_ON
    assert _state(hass, config_entry, "sensor", "phase").state == "period"
    assert _state(hass, config_entry, "sensor", "cycle_day").state == "3"


async def test_confirmation_sensor_disabled_by_default(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    entity_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{loaded_entry.unique_id}_awaiting_period_confirmation"
    )
    entry = er.async_get(hass).async_get(entity_id)
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_entities_share_one_service_device(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    devices = dr.async_entries_for_config_entry(
        dr.async_get(hass), loaded_entry.entry_id
    )
    assert len(devices) == 1
    assert devices[0].name == "Partner"
    assert devices[0].entry_type is dr.DeviceEntryType.SERVICE
    assert devices[0].model == "Clue Connect"


async def test_no_measurements_exposed(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Symptom-level data must never reach states or attributes."""
    for state in hass.states.async_all():
        assert "measurements" not in state.attributes
