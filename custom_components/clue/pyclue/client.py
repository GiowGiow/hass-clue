"""Synchronous HTTP client for the Clue Period Tracker API.

Clue has no public API. Endpoints here were verified against the live
service, but they may change without notice.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import requests

from .exceptions import (
    ClueAPIError,
    ClueAuthError,
    ClueConnectionNotFound,
    ClueNoDataError,
)
from .models import Calendar, Connection, ConnectionType, CycleSettings, User

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.helloclue.com"
DEFAULT_TIMEOUT = 15

# Clue's Android app build this specification was derived from. Sent so that
# requests look like a supported client rather than an unidentified one.
USER_AGENT = "Clue/231.0 (Android)"


class ClueClient:
    """Client for a single Clue account.

    Build one with credentials and call :meth:`login`, or pass an
    ``access_token`` obtained earlier:

        client = ClueClient("user@example.com", "password")
        client.login()
        calendar = client.get_calendar()

    The client is not thread-safe; use one instance per thread.
    """

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        *,
        access_token: str | None = None,
        base_url: str = BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self._email = email
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(
            {"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        self._access_token: str | None = None
        self._user: User | None = None
        if access_token:
            self._set_token(access_token)

    # ---------------------------------------------------------------- context

    def __enter__(self) -> ClueClient:
        if not self._access_token:
            self.login()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()

    # ------------------------------------------------------------------- auth

    @property
    def access_token(self) -> str | None:
        """The current token, reusable to build a client without re-login."""
        return self._access_token

    @property
    def user(self) -> User | None:
        """The account from the last login or :meth:`get_user` call."""
        return self._user

    def _set_token(self, token: str) -> None:
        self._access_token = token
        self._session.headers["Authorization"] = f"Token {token}"

    def login(self) -> User:
        """Authenticate and store the access token on this client.

        Raises:
            ClueAuthError: credentials are missing or rejected.
        """
        if not self._email or not self._password:
            raise ClueAuthError("email and password are required to log in")

        response = self._session.post(
            f"{self._base_url}/access-tokens",
            json={"email": self._email, "password": self._password},
            timeout=self._timeout,
        )
        if response.status_code == 401:
            raise ClueAuthError("invalid Clue credentials")
        payload = self._decode(response, "/access-tokens")

        token = payload.get("access_token")
        if not token:
            raise ClueAuthError("login response did not contain an access_token")
        self._set_token(token)
        self._user = User.from_payload(payload.get("user") or {})
        return self._user

    def logout(self) -> None:
        """Invalidate the current token server-side and forget it locally."""
        if self._access_token:
            try:
                self._session.post(
                    f"{self._base_url}/v1/user/logout", timeout=self._timeout
                )
            except Exception as err:  # noqa: BLE001 - see below
                # Clearing local state matters more than the round trip, and
                # this runs on the way out of a context manager, where an
                # exception would mask the caller's own. Catch broadly: the
                # transport may raise outside requests' own hierarchy.
                _LOGGER.debug("logout request failed: %s", err)
        self._access_token = None
        self._session.headers.pop("Authorization", None)

    # --------------------------------------------------------------- requests

    def _decode(self, response: requests.Response, path: str) -> dict[str, Any]:
        """Turn a response into a payload, or raise the matching ClueError."""
        try:
            payload = response.json() if response.content else {}
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {"data": payload}

        if response.ok:
            return payload

        if response.status_code in (401, 403):
            raise ClueAuthError(
                f"{path} rejected the access token ({response.status_code}); "
                "log in again"
            )

        detail = payload.get("detail") or payload.get("error") or response.reason
        raise ClueAPIError(
            f"{path} failed with HTTP {response.status_code}: {detail}",
            status_code=response.status_code,
            payload=payload,
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._access_token:
            raise ClueAuthError("not authenticated; call login() first")
        try:
            response = self._session.get(
                f"{self._base_url}{path}", params=params, timeout=self._timeout
            )
        except requests.RequestException as err:
            raise ClueAPIError(f"{path} request failed: {err}") from err
        return self._decode(response, path)

    # ---------------------------------------------------------------- account

    def get_user(self) -> User:
        """Fetch the authenticated account's profile."""
        self._user = User.from_payload(self._get("/v1/user"))
        return self._user

    def initialize(self) -> dict[str, Any]:
        """Fetch the app's bootstrap payload (user, tier, features, settings).

        Returned as the raw decoded dict: the shape is broad and mostly
        irrelevant to cycle tracking.
        """
        return self._get("/v1/initialize")

    # ----------------------------------------------------------------- cycles

    def get_cycle_settings(self) -> CycleSettings:
        """Fetch prediction settings and expected cycle/period lengths."""
        return CycleSettings.from_payload(self._get("/v1/cycles/settings"))

    def get_current_cycle(self) -> dict[str, Any]:
        """Fetch the current cycle for the authenticated account.

        Raises:
            ClueNoDataError: the account has no tracked cycles. The API
                signals this with 400 Bad Request. An account that only
                reads a partner's shared calendar always hits this; use
                :meth:`get_connection_calendar` instead.
        """
        try:
            return self._get("/v1/cycles/current")
        except ClueAPIError as err:
            if err.status_code == 400:
                raise ClueNoDataError(
                    "no current cycle for this account; it has no tracked "
                    "periods, or its cycle data is shared from a partner "
                    "account via Clue Connect"
                ) from err
            raise

    def get_current_cycle_or_none(self) -> dict[str, Any] | None:
        """Like :meth:`get_current_cycle`, but None when there is no cycle."""
        try:
            return self.get_current_cycle()
        except ClueNoDataError:
            return None

    def get_cycle_history(self) -> list[dict[str, Any]]:
        """Fetch past cycles for the authenticated account.

        Returns an empty list for an account with no tracked cycles.
        """
        return list(self._get("/v1/cycles/history").get("cycles") or ())

    def get_cycle_analysis(self) -> dict[str, Any]:
        """Fetch cycle length and variation statistics.

        Fields are null while Clue has too little data; the
        ``cycleLengthDetails.classification`` field reports that as
        ``not_enough_data``.
        """
        return self._get("/v1/cycles/analysis")

    # --------------------------------------------------------------- calendar

    @staticmethod
    def _date_window(
        start: date | None, end: date | None, *, past_days: int, future_days: int
    ) -> tuple[date, date]:
        today = date.today()
        start = start or today - timedelta(days=past_days)
        end = end or today + timedelta(days=future_days)
        if end < start:
            raise ValueError(f"end date {end} is before start date {start}")
        return start, end

    def get_calendar(
        self,
        start: date | None = None,
        end: date | None = None,
        *,
        past_days: int = 30,
        future_days: int = 60,
    ) -> Calendar:
        """Fetch the authenticated account's own calendar.

        Defaults to a window around today. Note that this endpoint only
        returns phases for an account that tracks its own cycles; for a
        partner account, use :meth:`get_connection_calendar`.
        """
        start, end = self._date_window(
            start, end, past_days=past_days, future_days=future_days
        )
        payload = self._get(
            "/v1/calendar",
            # The live API requires startDate/endDate, despite the
            # reverse-engineered spec documenting from/to.
            {"startDate": start.isoformat(), "endDate": end.isoformat()},
        )
        return Calendar.from_payload(payload)

    def get_connection_calendar(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
        *,
        past_days: int = 30,
        future_days: int = 60,
    ) -> Calendar:
        """Fetch a calendar shared through Clue Connect.

        Args:
            code: the connection code from :meth:`get_connections`.
            start: first day to fetch; defaults to ``past_days`` ago.
            end: last day to fetch; defaults to ``future_days`` ahead.

        Raises:
            ClueConnectionNotFound: the code does not match a connection.
        """
        start, end = self._date_window(
            start, end, past_days=past_days, future_days=future_days
        )
        try:
            payload = self._get(
                f"/v1/calendar/connections/{code}",
                {"startDate": start.isoformat(), "endDate": end.isoformat()},
            )
        except ClueAPIError as err:
            if err.status_code in (400, 404):
                raise ClueConnectionNotFound(
                    f"no Clue Connect calendar for code {code!r}"
                ) from err
            raise
        return Calendar.from_payload(payload)

    # ------------------------------------------------------------ connections

    def get_connections(self) -> list[Connection]:
        """List the account's Clue Connect links."""
        payload = self._get("/v1/connections")
        return [
            Connection.from_payload(item)
            for item in payload.get("connections") or ()
        ]

    def find_shared_calendar_code(self) -> str | None:
        """The code of the first active connection, or None when there is none.

        Convenience for the common setup of exactly one partner link, so a
        caller does not have to hardcode a connection code.
        """
        for connection in self.get_connections():
            if connection.is_active:
                return connection.code
        return None

    # ----------------------------------------------------------- measurements

    def get_measurements(
        self, start: date | None = None, end: date | None = None
    ) -> list[dict[str, Any]]:
        """Fetch raw measurements for the authenticated account's own window."""
        start, end = self._date_window(start, end, past_days=30, future_days=0)
        payload = self._get(
            "/v1/measurements",
            {"startDate": start.isoformat(), "endDate": end.isoformat()},
        )
        return list(payload.get("measurements") or ())

    # ------------------------------------------------------------- high level

    def resolve_calendar(
        self,
        code: str | None = None,
        start: date | None = None,
        end: date | None = None,
        *,
        past_days: int = 30,
        future_days: int = 60,
    ) -> Calendar:
        """Fetch a calendar from whichever source this account has data in.

        Tries, in order: the given connection code, the account's own
        calendar when it has tracked cycles, then its first active
        connection. This keeps a caller working whether the account owns
        the cycle data or reads a partner's.

        Raises:
            ClueNoDataError: no source on this account returned cycle data.
        """
        if code:
            return self.get_connection_calendar(
                code, start, end, past_days=past_days, future_days=future_days
            )

        if self.get_current_cycle_or_none() is not None:
            return self.get_calendar(
                start, end, past_days=past_days, future_days=future_days
            )

        for connection in self.get_connections():
            if not connection.is_active:
                continue
            # A host connection shares this account's data outward, so it is
            # not a readable calendar when the account has no cycles itself.
            if connection.type is ConnectionType.HOST:
                _LOGGER.debug(
                    "trying host connection %s as a calendar source", connection.code
                )
            try:
                return self.get_connection_calendar(
                    connection.code,
                    start,
                    end,
                    past_days=past_days,
                    future_days=future_days,
                )
            except ClueConnectionNotFound:
                continue

        raise ClueNoDataError(
            "no cycle data available: this account tracks no cycles and has "
            "no readable Clue Connect calendar"
        )
