"""Data update coordinator for the Clue integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CONNECTION_CODE,
    DOMAIN,
    FUTURE_DAYS,
    LOGGER,
    PAST_DAYS,
    SOURCE_OWN,
    UPDATE_INTERVAL,
)
from .pyclue import Calendar, ClueAPIError, ClueAuthError, ClueClient, ClueError, CycleState, derive

type ClueConfigEntry = ConfigEntry[ClueDataUpdateCoordinator]


class ClueDataUpdateCoordinator(DataUpdateCoordinator[CycleState]):
    """Fetch the Clue calendar and derive the current cycle state.

    The pyclue client is synchronous, so every call to it runs in the
    executor. Calls are never concurrent: the coordinator runs one refresh
    at a time, which matters because the client is not thread-safe.
    """

    config_entry: ClueConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ClueConfigEntry) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = ClueClient(entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
        code = entry.data.get(CONF_CONNECTION_CODE, SOURCE_OWN)
        self.connection_code: str | None = None if code == SOURCE_OWN else code

    async def _async_setup(self) -> None:
        """Log in once before the first refresh."""
        try:
            await self.hass.async_add_executor_job(self.client.login)
        except ClueAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ClueError as err:
            raise UpdateFailed(f"Could not log in to Clue: {err}") from err

    def _fetch_calendar(self) -> Calendar:
        if self.connection_code:
            return self.client.get_connection_calendar(
                self.connection_code, past_days=PAST_DAYS, future_days=FUTURE_DAYS
            )
        return self.client.get_calendar(past_days=PAST_DAYS, future_days=FUTURE_DAYS)

    def _fetch_calendar_with_relogin(self) -> Calendar:
        try:
            return self._fetch_calendar()
        except ClueAuthError:
            # Tokens expire; one fresh login distinguishes that from a
            # changed password, which makes login() itself raise.
            LOGGER.debug("Clue token rejected, logging in again")
            self.client.login()
            return self._fetch_calendar()

    async def _async_update_data(self) -> CycleState:
        try:
            calendar = await self.hass.async_add_executor_job(
                self._fetch_calendar_with_relogin
            )
        except ClueAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ClueAPIError as err:
            raise UpdateFailed(f"Error communicating with Clue: {err}") from err
        except ClueError as err:
            raise UpdateFailed(str(err)) from err

        # Use Home Assistant's timezone, not the host's, to decide what
        # "today" is: the cycle day turns over at local midnight.
        return derive(calendar, today=dt_util.now().date())
