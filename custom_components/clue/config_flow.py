"""Config flow for the Clue integration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_CONNECTION_CODE, DOMAIN, LOGGER, SOURCE_OWN
from .pyclue import ClueAuthError, ClueClient, ClueError, User

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)


@dataclass(frozen=True, slots=True)
class _Source:
    """A calendar this account can read: its own, or a shared one."""

    code: str
    title: str


@dataclass(frozen=True, slots=True)
class _AccountInfo:
    user: User
    sources: list[_Source]

    @property
    def account_id(self) -> str:
        # The login response carries the account id; the email is a stable
        # fallback should Clue ever drop it.
        return self.user.id or self.user.email.lower()


def _discover(email: str, password: str) -> _AccountInfo:
    """Log in and list the calendars that have cycle data.

    Runs in the executor: the pyclue client is synchronous.
    """
    client = ClueClient(email, password)
    try:
        user = client.login()

        sources: list[_Source] = []
        # An account that only reads a partner's calendar has no cycles of
        # its own; offering it would create an entry with no data.
        if client.get_current_cycle_or_none() is not None:
            sources.append(_Source(SOURCE_OWN, user.display_name))
        sources.extend(
            _Source(connection.code, connection.name or connection.code)
            for connection in client.get_connections()
            if connection.is_active
        )
        return _AccountInfo(user=user, sources=sources)
    finally:
        client.close()


class ClueConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Clue."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None
        self._account: _AccountInfo | None = None

    async def _async_validate(
        self, email: str, password: str
    ) -> tuple[_AccountInfo | None, dict[str, str]]:
        try:
            account = await self.hass.async_add_executor_job(_discover, email, password)
        except ClueAuthError:
            return None, {"base": "invalid_auth"}
        except ClueError:
            return None, {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001 - surfaced to the user as "unknown"
            LOGGER.exception("Unexpected error while setting up Clue")
            return None, {"base": "unknown"}
        return account, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the Clue account credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            account, errors = await self._async_validate(
                user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if account is not None:
                if not account.sources:
                    return self.async_abort(reason="no_data")
                self._email = user_input[CONF_EMAIL]
                self._password = user_input[CONF_PASSWORD]
                self._account = account
                if len(account.sources) == 1:
                    return await self._async_create(account.sources[0])
                return await self.async_step_source()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_source(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which calendar to track when the account can read several."""
        assert self._account is not None
        sources = {source.code: source for source in self._account.sources}

        if user_input is not None:
            return await self._async_create(sources[user_input[CONF_CONNECTION_CODE]])

        return self.async_show_form(
            step_id="source",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONNECTION_CODE): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=source.code, label=source.title)
                                for source in self._account.sources
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def _async_create(self, source: _Source) -> ConfigFlowResult:
        assert self._account is not None
        await self.async_set_unique_id(f"{self._account.account_id}_{source.code}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=source.title,
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
                CONF_CONNECTION_CODE: source.code,
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after Clue rejected the stored password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            account, errors = await self._async_validate(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if account is not None:
                code = entry.data[CONF_CONNECTION_CODE]
                await self.async_set_unique_id(f"{account.account_id}_{code}")
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )
