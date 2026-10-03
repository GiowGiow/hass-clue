"""Tests for the Clue config flow."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.clue.const import CONF_CONNECTION_CODE, DOMAIN, SOURCE_OWN
from custom_components.clue.pyclue import ClueAPIError, ClueAuthError, User

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import ACCOUNT_ID, PARTNER_CODE

CREDENTIALS = {CONF_EMAIL: "alex@example.com", CONF_PASSWORD: "secret"}

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


async def _start(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_single_source_creates_entry(
    hass: HomeAssistant, mock_clue_client: MagicMock
) -> None:
    """A partner account with one connection skips the source step."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Partner"
    assert result["data"] == {**CREDENTIALS, CONF_CONNECTION_CODE: PARTNER_CODE}
    assert result["result"].unique_id == f"{ACCOUNT_ID}_{PARTNER_CODE}"
    mock_clue_client.close.assert_called()


async def test_several_sources_asks_which(
    hass: HomeAssistant, mock_clue_client: MagicMock
) -> None:
    """An account with own cycles and a connection picks between them."""
    mock_clue_client.get_current_cycle_or_none.return_value = {"cycle": {}}

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "source"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONNECTION_CODE: SOURCE_OWN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Alex"
    assert result["data"][CONF_CONNECTION_CODE] == SOURCE_OWN
    assert result["result"].unique_id == f"{ACCOUNT_ID}_{SOURCE_OWN}"


async def test_inactive_connections_are_ignored(
    hass: HomeAssistant, mock_clue_client: MagicMock
) -> None:
    pending = MagicMock(is_active=False, code="pending", name="Pending")
    mock_clue_client.get_connections.return_value = [pending]

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_data"


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (ClueAuthError("bad"), "invalid_auth"),
        (ClueAPIError("down", status_code=503), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_errors_recover(
    hass: HomeAssistant,
    mock_clue_client: MagicMock,
    side_effect: Exception,
    error: str,
) -> None:
    """Each error shows on the form, and a retry then succeeds."""
    mock_clue_client.login.side_effect = side_effect

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_clue_client.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_aborts(
    hass: HomeAssistant,
    mock_clue_client: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_password(
    hass: HomeAssistant,
    mock_clue_client: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_PASSWORD] == "new-secret"


async def test_reauth_invalid_password_recovers(
    hass: HomeAssistant,
    mock_clue_client: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)
    mock_clue_client.login.side_effect = ClueAuthError("bad")

    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_clue_client.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )
    assert result["reason"] == "reauth_successful"


async def test_reauth_rejects_other_account(
    hass: HomeAssistant,
    mock_clue_client: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)
    mock_clue_client.login.return_value = User(email="other@example.com", id="other")

    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert config_entry.data[CONF_PASSWORD] == "secret"
