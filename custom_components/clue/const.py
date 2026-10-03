"""Constants for the Clue integration."""

from __future__ import annotations

from datetime import timedelta
import logging

DOMAIN = "clue"
LOGGER = logging.getLogger(__package__)

CONF_CONNECTION_CODE = "connection_code"

# Value stored in CONF_CONNECTION_CODE when the entry reads the account's own
# cycles rather than a calendar shared through Clue Connect.
SOURCE_OWN = "own"

UPDATE_INTERVAL = timedelta(hours=1)

# Calendar window fetched on each update. Sixty days back finds the last
# period even in a long cycle; ninety days ahead covers the next period and
# the ovulation after it.
PAST_DAYS = 60
FUTURE_DAYS = 90
