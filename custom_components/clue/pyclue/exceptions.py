"""Exception hierarchy for the Clue API client."""

from __future__ import annotations


class ClueError(Exception):
    """Base class for every error raised by this library."""


class ClueAuthError(ClueError):
    """Raised when credentials are rejected or a token is no longer valid."""


class ClueAPIError(ClueError):
    """Raised for an unexpected HTTP response from the Clue API.

    Attributes:
        status_code: HTTP status returned by the API.
        payload: Decoded JSON error body, or None when the body was not JSON.
        request_id: Clue's ``requestId``, useful when reporting an issue.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.request_id = self.payload.get("requestId")


class ClueNoDataError(ClueError):
    """Raised when an endpoint has no data to return for this account.

    The Clue API answers 400 Bad Request (rather than 404 or 204) for some
    endpoints when the account has no tracked cycles. Callers that treat
    "no data yet" as a normal state should use the ``*_or_none`` helpers
    instead of catching this.
    """


class ClueConnectionNotFound(ClueError):
    """Raised when no Clue Connect connection matches the requested code."""
