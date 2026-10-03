"""Typed models for the Clue API payloads.

Shapes here follow what the live API actually returns (verified against
api.helloclue.com), which diverges from the reverse-engineered OpenAPI spec
in a few places. Notably, a phase carries ``position``/``level`` rather than
the ``startDate``/``endDate`` the spec describes.

Every model keeps the decoded payload in ``raw`` so that fields this library
does not model yet remain reachable without a release.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


class PhaseType(str, Enum):
    """Cycle phase kinds returned by the calendar endpoints.

    ``PERIOD`` is a tracked period; ``PREDICTED_*`` members are forecasts.
    """

    PERIOD = "period"
    PREDICTED_PERIOD = "predictedPeriod"
    FERTILE = "fertile"
    PREDICTED_FERTILE = "predictedFertile"
    OVULATION = "ovulation"
    PREDICTED_OVULATION = "predictedOvulation"
    PMS = "pms"
    CONCEPTION = "conception"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> PhaseType:
        # The API may add phase types; an unknown one must not break parsing.
        return cls.UNKNOWN

    @property
    def is_predicted(self) -> bool:
        return self.value.startswith("predicted")


class PeriodLevel(str, Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    SPOTTING = "spotting"
    NONE = "none"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> PeriodLevel:
        return cls.UNKNOWN


class PhasePosition(str, Enum):
    """Where a day sits inside a multi-day phase."""

    START = "start"
    MIDDLE = "middle"
    END = "end"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> PhasePosition:
        return cls.UNKNOWN


@dataclass(frozen=True, slots=True)
class Phase:
    """One phase marker attached to a single calendar day."""

    type: PhaseType
    position: PhasePosition | None = None
    level: PeriodLevel | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Phase:
        level = payload.get("level")
        position = payload.get("position")
        return cls(
            type=PhaseType(payload.get("type")),
            position=PhasePosition(position) if position else None,
            level=PeriodLevel(level) if level else None,
            raw=payload,
        )

    @property
    def is_period(self) -> bool:
        """True for a tracked or predicted period phase."""
        return self.type in (PhaseType.PERIOD, PhaseType.PREDICTED_PERIOD)

    @property
    def is_fertile(self) -> bool:
        return self.type in (PhaseType.FERTILE, PhaseType.PREDICTED_FERTILE)

    @property
    def is_ovulation(self) -> bool:
        return self.type in (PhaseType.OVULATION, PhaseType.PREDICTED_OVULATION)


@dataclass(frozen=True, slots=True)
class Measurement:
    """A single tracked data point, such as ``feelings`` or ``weight``.

    ``value`` keeps the API's own structure, which varies per ``type``:
    a list of ``{"option": ...}`` entries, or an object such as
    ``{"kilograms": 70.5}`` or ``{"minutes": 480}``.
    """

    type: str
    date: date
    value: Any
    id: str | None = None
    source: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Measurement:
        return cls(
            type=payload["type"],
            date=_parse_date(payload["date"]),
            value=payload.get("value"),
            id=payload.get("id"),
            source=payload.get("source"),
            raw=payload,
        )

    @property
    def options(self) -> list[str]:
        """The selected option names, for the option-list measurement types.

        Returns an empty list for measurement types whose value is not an
        option list (for example ``weight`` or ``sleep_duration``).
        """
        value = self.value
        if isinstance(value, dict):
            option = value.get("option")
            return [option] if isinstance(option, str) else []
        if isinstance(value, list):
            return [
                entry["option"]
                for entry in value
                if isinstance(entry, dict) and isinstance(entry.get("option"), str)
            ]
        return []


@dataclass(frozen=True, slots=True)
class Day:
    """One day of the Clue calendar."""

    date: date
    cycle_day: int | None = None
    phases: tuple[Phase, ...] = ()
    measurements: tuple[Measurement, ...] = ()
    category_groups: tuple[str, ...] = ()
    period_level: PeriodLevel | None = None
    birth_control_pill: str | None = None
    pregnancy: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Day:
        cycle = payload.get("cycle") or {}
        period_measurement = payload.get("periodMeasurement") or {}
        period_value = (period_measurement.get("value") or {}).get("option")
        return cls(
            date=_parse_date(payload["date"]),
            cycle_day=cycle.get("day"),
            phases=tuple(
                Phase.from_payload(item) for item in payload.get("phases") or ()
            ),
            measurements=tuple(
                Measurement.from_payload(item)
                for item in payload.get("measurements") or ()
            ),
            category_groups=tuple(payload.get("categoryGroups") or ()),
            period_level=PeriodLevel(period_value) if period_value else None,
            birth_control_pill=payload.get("birthControlPill"),
            pregnancy=payload.get("pregnancy"),
            raw=payload,
        )

    def phase_types(self) -> set[PhaseType]:
        return {phase.type for phase in self.phases}

    def has_phase(self, *types: PhaseType) -> bool:
        wanted = set(types)
        return any(phase.type in wanted for phase in self.phases)

    @property
    def in_period(self) -> bool:
        """True when a period (tracked or predicted) covers this day."""
        return any(phase.is_period for phase in self.phases)

    @property
    def in_fertile_window(self) -> bool:
        return any(phase.is_fertile for phase in self.phases)

    @property
    def is_ovulation(self) -> bool:
        return any(phase.is_ovulation for phase in self.phases)

    def measurement(self, type_: str) -> Measurement | None:
        """The first measurement of ``type_``, or None when not tracked."""
        for measurement in self.measurements:
            if measurement.type == type_:
                return measurement
        return None


@dataclass(frozen=True, slots=True)
class PeriodConfirmation:
    """Dates Clue predicted as a period and is waiting to be confirmed."""

    predicted_period_dates: tuple[date, ...] = ()
    untracked_period_dates: tuple[date, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> PeriodConfirmation | None:
        if not payload:
            return None
        return cls(
            predicted_period_dates=tuple(
                _parse_date(value)
                for value in payload.get("predictedPeriodDates") or ()
            ),
            untracked_period_dates=tuple(
                _parse_date(value)
                for value in payload.get("untrackedPeriodDates") or ()
            ),
            raw=payload,
        )


@dataclass(frozen=True, slots=True)
class Calendar:
    """A date-ordered window of calendar days.

    Returned by both the own-account and the Clue Connect calendar calls, so
    downstream derivation works the same for either data source.
    """

    days: tuple[Day, ...]
    max_calendar_date: date | None = None
    period_confirmation: PeriodConfirmation | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Calendar:
        days = tuple(
            sorted(
                (Day.from_payload(item) for item in payload.get("days") or ()),
                key=lambda day: day.date,
            )
        )
        return cls(
            days=days,
            max_calendar_date=_parse_date(payload.get("maxCalendarDate")),
            period_confirmation=PeriodConfirmation.from_payload(
                payload.get("periodConfirmation")
            ),
            raw=payload,
        )

    def __len__(self) -> int:
        return len(self.days)

    def __iter__(self):
        return iter(self.days)

    def day(self, when: date) -> Day | None:
        """The day matching ``when``, or None when outside this window."""
        for item in self.days:
            if item.date == when:
                return item
        return None


class ConnectionType(str, Enum):
    """Which side of a Clue Connect link this account is on.

    ``HOST`` means this account owns the cycle data and shares it out.
    ``GUEST`` means this account reads someone else's shared calendar.
    """

    HOST = "host"
    GUEST = "guest"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> ConnectionType:
        return cls.UNKNOWN


@dataclass(frozen=True, slots=True)
class Connection:
    """A Clue Connect partner link."""

    code: str
    type: ConnectionType
    status: str
    name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Connection:
        return cls(
            code=payload["code"],
            type=ConnectionType(payload.get("type")),
            status=payload.get("status", "unknown"),
            name=payload.get("name"),
            raw=payload,
        )

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True, slots=True)
class User:
    """The authenticated Clue account."""

    email: str
    first_name: str | None = None
    last_name: str | None = None
    id: str | None = None
    mode: str | None = None
    email_verified: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> User:
        # /access-tokens uses snake_case, /v1/user uses camelCase.
        return cls(
            email=payload.get("email", ""),
            first_name=payload.get("firstName") or payload.get("first_name"),
            last_name=payload.get("lastName") or payload.get("last_name"),
            id=payload.get("id"),
            mode=payload.get("mode"),
            email_verified=bool(
                payload.get("emailVerified") or payload.get("email_verified")
            ),
            raw=payload,
        )

    @property
    def display_name(self) -> str:
        name = " ".join(part for part in (self.first_name, self.last_name) if part)
        return name or self.email


@dataclass(frozen=True, slots=True)
class CycleSettings:
    """Cycle prediction settings for the account."""

    fertile_phase_enabled: bool = False
    ovulation_phase_enabled: bool = False
    predicted_cycle_length: int | None = None
    predicted_period_length: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CycleSettings:
        cycle_length = payload.get("cycleLengthSettings") or {}
        period_length = payload.get("periodLengthSettings") or {}

        def _effective(settings: dict[str, Any]) -> int | None:
            # Clue keeps a manual override next to its own prediction and
            # picks between them with the `manualPrediction` flag.
            if settings.get("manualPrediction"):
                return settings.get("manualPredictedValue")
            return settings.get("cluePredictedValue") or settings.get(
                "manualPredictedValue"
            )

        return cls(
            fertile_phase_enabled=bool(payload.get("fertilePhaseEnabled")),
            ovulation_phase_enabled=bool(payload.get("ovulationPhaseEnabled")),
            predicted_cycle_length=_effective(cycle_length),
            predicted_period_length=_effective(period_length),
            raw=payload,
        )
