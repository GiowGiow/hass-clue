"""Tests for setup, unload and coordinator behavior."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.clue.const import DOMAIN, UPDATE_INTERVAL
from custom_components.clue.pyclue import ClueAPIError, ClueAuthError

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import FROZEN_TIME, PARTNER_CODE


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str, platform: str = "sensor") -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.unique_id}_{key}"
    )
    assert entity_id is not None
    return entity_id


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.freeze_time(FROZEN_TIME)
async def test_setup_and_unload(
    hass: HomeAssistant, mock_clue_client: MagicMock, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    mock_clue_client.get_connection_calendar.assert_called_with(
        PARTNER_CODE, past_days=60, future_days=90
    )

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    mock_clue_client.close.assert_called_once()


@pytest.mark.freeze_time(FROZEN_TIME)
async def test_own_entry_reads_own_calendar(
    hass: HomeAssistant, mock_clue_client: MagicMock, own_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, own_config_entry)
    assert own_config_entry.state is ConfigEntryState.LOADED
    mock_clue_client.get_calendar.assert_called_with(past_days=60, future_days=90)
    mock_clue_client.get_connection_calendar.assert_not_called()


async def test_login_rejected_starts_reauth(
    hass: HomeAssistant, mock_clue_client: MagicMock, config_entry: MockConfigEntry
) -> None:
    mock_clue_client.login.side_effect = ClueAuthError("bad")
    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_api_error_retries_setup(
    hass: HomeAssistant, mock_clue_client: MagicMock, config_entry: MockConfigEntry
) -> None:
    mock_clue_client.get_connection_calendar.side_effect = ClueAPIError(
        "down", status_code=503
    )
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.freeze_time(FROZEN_TIME)
async def test_expired_token_logs_in_again(
    hass: HomeAssistant,
    mock_clue_client: MagicMock,
    config_entry: MockConfigEntry,
    calendar,
) -> None:
    mock_clue_client.get_connection_calendar.side_effect = [
        ClueAuthError("expired"),
        calendar,
    ]
    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert mock_clue_client.login.call_count == 2
    assert hass.states.get(_entity_id(hass, config_entry, "cycle_day")).state == "20"


@pytest.mark.freeze_time(FROZEN_TIME)
async def test_password_changed_during_update_starts_reauth(
    hass: HomeAssistant,
    mock_clue_client: MagicMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, config_entry)

    mock_clue_client.get_connection_calendar.side_effect = ClueAuthError("expired")
    mock_clue_client.login.side_effect = ClueAuthError("bad password")
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


@pytest.mark.freeze_time(FROZEN_TIME)
async def test_update_failure_marks_entities_unavailable(
    hass: HomeAssistant,
    mock_clue_client: MagicMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, config_entry, "cycle_day")
    assert hass.states.get(entity_id).state == "20"

    mock_clue_client.get_connection_calendar.side_effect = ClueAPIError(
        "down", status_code=503
    )
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


@pytest.mark.freeze_time("2025-05-21 23:30:00-03:00")
async def test_refreshes_at_local_midnight(
    hass: HomeAssistant,
    mock_clue_client: MagicMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The cycle day advances right after midnight, not on the next poll."""
    await hass.config.async_set_time_zone("America/Sao_Paulo")
    await _setup(hass, config_entry)
    entity_id = _entity_id(hass, config_entry, "cycle_day")
    assert hass.states.get(entity_id).state == "20"
    calls = mock_clue_client.get_connection_calendar.call_count

    # Set up at 23:30, so the next hourly poll is due at 00:30. Moving to
    # 00:00:10 only crosses the midnight trigger.
    freezer.tick(timedelta(minutes=30, seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert mock_clue_client.get_connection_calendar.call_count == calls + 1
    assert hass.states.get(entity_id).state == "21"
