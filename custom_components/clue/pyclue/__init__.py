"""Unofficial Python client for the Clue period tracker API.

Built for a Home Assistant integration, but usable on its own:

    from pyclue import ClueClient, derive

    with ClueClient("user@example.com", "password") as client:
        state = derive(client.resolve_calendar())
        print(state.cycle_day, state.phase_label, state.days_until_next_period)

Clue publishes no API. Endpoints were verified against the live service and
may change without notice.
"""

from .client import BASE_URL, ClueClient
from .cycle import (
    CyclePhase,
    CycleState,
    PeriodWindow,
    derive,
    ovulation_cycle_day,
    period_windows,
)
from .exceptions import (
    ClueAPIError,
    ClueAuthError,
    ClueConnectionNotFound,
    ClueError,
    ClueNoDataError,
)
from .models import (
    Calendar,
    Connection,
    ConnectionType,
    CycleSettings,
    Day,
    Measurement,
    PeriodConfirmation,
    PeriodLevel,
    Phase,
    PhasePosition,
    PhaseType,
    User,
)

__version__ = "0.1.0"

__all__ = [
    "BASE_URL",
    "Calendar",
    "ClueAPIError",
    "ClueAuthError",
    "ClueClient",
    "ClueConnectionNotFound",
    "ClueError",
    "ClueNoDataError",
    "Connection",
    "ConnectionType",
    "CyclePhase",
    "CycleSettings",
    "CycleState",
    "Day",
    "Measurement",
    "PeriodConfirmation",
    "PeriodLevel",
    "PeriodWindow",
    "Phase",
    "PhasePosition",
    "PhaseType",
    "User",
    "__version__",
    "derive",
    "ovulation_cycle_day",
    "period_windows",
]
