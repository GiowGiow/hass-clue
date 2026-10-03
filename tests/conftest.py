"""Fixtures for the Clue integration tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from custom_components.clue.const import CONF_CONNECTION_CODE, DOMAIN, SOURCE_OWN
from custom_components.clue.pyclue import (
    Calendar,
    Connection,
    ConnectionType,
    User,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry

# Reference day for every test. The synthetic calendar puts it on cycle day 20.
TODAY = date(2025, 5, 21)
FROZEN_TIME = "2025-05-21 12:00:00-03:00"

ACCOUNT_ID = "account-1"
PARTNER_CODE = "partner-code"
USER = User(email="alex@example.com", first_name="Alex", id=ACCOUNT_ID)
PARTNER = Connection(
    code=PARTNER_CODE, type=ConnectionType.HOST, status="active", name="Partner"
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load integrations from custom_components in every test."""


def build_calendar(today: date = TODAY, cycle_length: int = 28) -> Calendar:
    """A synthetic calendar with today on cycle day 20.

    The current cycle started 19 days before ``today``. Each cycle has a
    4-day period, a fertile window on days 10-16 and ovulation on day 15.
    Days before ``today`` carry tracked periods; later ones predictions.
    """
    cycle_start = today - timedelta(days=19)
    days = []
    for offset in range(-10, 50):
        when = cycle_start + timedelta(days=offset)
        cycle_day = offset % cycle_length + 1
        phases: list[dict] = []
        if cycle_day <= 4:
            position = {1: "start", 4: "end"}.get(cycle_day, "middle")
            kind = "period" if when < today else "predictedPeriod"
            phases.append({"type": kind, "level": "medium", "position": position})
        if 10 <= cycle_day <= 16:
            position = {10: "start", 16: "end"}.get(cycle_day, "middle")
            phases.append({"type": "predictedFertile", "position": position})
        if cycle_day == 15:
            phases.append({"type": "predictedOvulation"})
        days.append(
            {
                "date": when.isoformat(),
                "cycle": {"day": cycle_day},
                "phases": phases,
                "measurements": [],
            }
        )
    return Calendar.from_payload(
        {"maxCalendarDate": (today + timedelta(days=365)).isoformat(), "days": days}
    )


@pytest.fixture
def calendar() -> Calendar:
    return build_calendar()


@pytest.fixture
def mock_clue_client(calendar: Calendar) -> Generator[MagicMock]:
    """Patch ClueClient everywhere the integration builds one.

    Defaults model a partner account: no cycles of its own, one active
    Clue Connect link.
    """
    client = MagicMock()
    client.login.return_value = USER
    client.get_current_cycle_or_none.return_value = None
    client.get_connections.return_value = [PARTNER]
    client.get_connection_calendar.return_value = calendar
    client.get_calendar.return_value = calendar
    with (
        patch("custom_components.clue.coordinator.ClueClient", return_value=client),
        patch("custom_components.clue.config_flow.ClueClient", return_value=client),
    ):
        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[MagicMock]:
    """Skip entry setup in config flow tests."""
    with patch(
        "custom_components.clue.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Partner",
        unique_id=f"{ACCOUNT_ID}_{PARTNER_CODE}",
        data={
            CONF_EMAIL: USER.email,
            CONF_PASSWORD: "secret",
            CONF_CONNECTION_CODE: PARTNER_CODE,
        },
    )


@pytest.fixture
def own_config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Alex",
        unique_id=f"{ACCOUNT_ID}_{SOURCE_OWN}",
        data={
            CONF_EMAIL: USER.email,
            CONF_PASSWORD: "secret",
            CONF_CONNECTION_CODE: SOURCE_OWN,
        },
    )
