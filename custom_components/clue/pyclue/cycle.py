"""Derive cycle state from a calendar window.

The Clue API reports phases per day, but a Home Assistant sensor wants
aggregates: which phase today is in, when the next period starts, how many
days until it does. This module does that derivation, with no I/O, so it can
be unit-tested against recorded payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from enum import Enum
from typing import Any

from .models import Calendar, Day, PeriodLevel, PhasePosition, PhaseType


class CyclePhase(str, Enum):
    """The phase a single day is reported as being in.

    This collapses tracked and predicted phases into one value, since a
    sensor cares about the phase and not about how it was derived. Use
    :attr:`CycleState.is_predicted` to tell the two apart.
    """

    PERIOD = "period"
    FERTILE = "fertile"
    OVULATION = "ovulation"
    PMS = "pms"
    FOLLICULAR = "follicular"
    LUTEAL = "luteal"
    UNKNOWN = "unknown"


# Checked in order: a day can carry several phases at once (ovulation days
# also sit inside the fertile window), and the most specific one wins.
_PHASE_PRIORITY: tuple[tuple[CyclePhase, tuple[PhaseType, ...]], ...] = (
    (CyclePhase.PERIOD, (PhaseType.PERIOD, PhaseType.PREDICTED_PERIOD)),
    (CyclePhase.OVULATION, (PhaseType.OVULATION, PhaseType.PREDICTED_OVULATION)),
    (CyclePhase.FERTILE, (PhaseType.FERTILE, PhaseType.PREDICTED_FERTILE)),
    (CyclePhase.PMS, (PhaseType.PMS,)),
)


def phase_of(day: Day, ovulation_day: int | None = None) -> CyclePhase:
    """The phase of a single day.

    Clue only marks period, fertile and ovulation phases. The follicular and
    luteal phases are inferred from the day's position relative to
    ``ovulation_day`` when that is known, so that an ordinary mid-cycle day
    gets a meaningful phase rather than ``UNKNOWN``.

    Args:
        day: the day to classify.
        ovulation_day: the cycle day ovulation falls on, from
            :func:`ovulation_cycle_day`. Without it, an unmarked day is
            ``UNKNOWN``.
    """
    types = day.phase_types()
    for phase, candidates in _PHASE_PRIORITY:
        if types.intersection(candidates):
            return phase

    if day.cycle_day is None or ovulation_day is None:
        return CyclePhase.UNKNOWN
    if day.cycle_day <= ovulation_day:
        return CyclePhase.FOLLICULAR
    return CyclePhase.LUTEAL


def ovulation_cycle_day(calendar: Calendar, today: date | None = None) -> int | None:
    """The cycle day that ovulation falls on, as a cycle-relative offset.

    Using Clue's own marked ovulation keeps the inferred follicular/luteal
    split consistent with its predictions rather than a textbook 14-day
    assumption.

    The window usually spans more than one cycle, and ``cycle_day`` restarts
    at 1 with each period, so ovulation days from different cycles are not
    comparable. The day nearest ``today`` is used, since that is the cycle a
    caller is asking about. Returns None when the window marks no ovulation.
    """
    today = today or date.today()
    candidates = [
        day for day in calendar.days if day.is_ovulation and day.cycle_day is not None
    ]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda day: abs((day.date - today).days))
    return nearest.cycle_day


@dataclass(frozen=True, slots=True)
class PeriodWindow:
    """A contiguous run of period days."""

    start: date
    end: date
    predicted: bool
    levels: tuple[PeriodLevel, ...] = ()

    @property
    def length(self) -> int:
        return (self.end - self.start).days + 1

    def __contains__(self, when: date) -> bool:
        return self.start <= when <= self.end


def period_windows(calendar: Calendar) -> list[PeriodWindow]:
    """Group the calendar's period days into contiguous windows.

    Days are grouped by adjacency rather than by the ``position`` marker,
    because a window clipped by the calendar's own range has no ``start``
    or ``end`` day in the payload.
    """
    windows: list[PeriodWindow] = []
    run: list[Day] = []

    def flush() -> None:
        if not run:
            return
        predicted = any(
            phase.type is PhaseType.PREDICTED_PERIOD
            for day in run
            for phase in day.phases
            if phase.is_period
        )
        windows.append(
            PeriodWindow(
                start=run[0].date,
                end=run[-1].date,
                predicted=predicted,
                levels=tuple(day.period_level for day in run if day.period_level),
            )
        )
        run.clear()

    for day in calendar.days:
        if not day.in_period:
            flush()
            continue
        # A gap in the data, or a fresh window starting right after another,
        # both end the current run.
        starts_new_window = any(
            phase.is_period and phase.position is PhasePosition.START
            for phase in day.phases
        )
        if run and (
            (day.date - run[-1].date).days > 1 or (starts_new_window and len(run) > 1)
        ):
            flush()
        run.append(day)
    flush()

    return windows


@dataclass(frozen=True, slots=True)
class CycleState:
    """Everything a Home Assistant entity needs from one calendar fetch.

    Built by :func:`derive`. Every field is either a plain scalar or a date,
    so it maps directly onto sensor state without further processing.
    """

    as_of: date
    cycle_day: int | None = None
    phase: CyclePhase = CyclePhase.UNKNOWN
    is_predicted: bool = False
    in_period: bool = False
    in_fertile_window: bool = False
    is_ovulation_day: bool = False
    period_level: PeriodLevel | None = None
    current_period_start: date | None = None
    last_period_start: date | None = None
    last_period_end: date | None = None
    last_period_length: int | None = None
    next_period_start: date | None = None
    next_period_end: date | None = None
    days_until_next_period: int | None = None
    next_ovulation: date | None = None
    days_until_next_ovulation: int | None = None
    fertile_window_start: date | None = None
    fertile_window_end: date | None = None
    tracked_categories: tuple[str, ...] = ()
    awaiting_period_confirmation: bool = False
    calendar_end: date | None = None

    @property
    def phase_label(self) -> str:
        """The phase as a sensor-ready string."""
        return self.phase.value

    def as_dict(self) -> dict[str, Any]:
        """A JSON-friendly mapping, with dates as ISO strings.

        Convenient for a Home Assistant coordinator or for caching a fetch.
        """
        result: dict[str, Any] = {}
        for item in fields(self):
            name = item.name
            value = getattr(self, name)
            if isinstance(value, date):
                result[name] = value.isoformat()
            elif isinstance(value, Enum):
                result[name] = value.value
            elif isinstance(value, tuple):
                result[name] = list(value)
            else:
                result[name] = value
        return result


def _fertile_bounds(
    calendar: Calendar, today: date
) -> tuple[date | None, date | None]:
    """The fertile window covering today, or the next upcoming one."""
    runs: list[list[date]] = []
    for day in calendar.days:
        if day.in_fertile_window:
            if runs and (day.date - runs[-1][-1]).days == 1:
                runs[-1].append(day.date)
            else:
                runs.append([day.date])

    for run in runs:
        if run[0] <= today <= run[-1]:
            return run[0], run[-1]
    for run in runs:
        if run[0] > today:
            return run[0], run[-1]
    return None, None


def derive(calendar: Calendar, today: date | None = None) -> CycleState:
    """Build a :class:`CycleState` from a calendar window.

    Args:
        calendar: a window that should span some past and some future days;
            fields depending on data outside the window are left None.
        today: the reference day; defaults to the current local date.
    """
    today = today or date.today()
    current = calendar.day(today)
    windows = period_windows(calendar)
    ovulation_day = ovulation_cycle_day(calendar, today)

    past = [w for w in windows if w.end < today and not w.predicted]
    covering = next((w for w in windows if today in w), None)
    upcoming = [w for w in windows if w.start > today]

    # A period covering today is the latest actual period, not an upcoming one.
    last = covering or (past[-1] if past else None)
    next_period = upcoming[0] if upcoming else None

    next_ovulation = next(
        (day.date for day in calendar.days if day.date >= today and day.is_ovulation),
        None,
    )
    fertile_start, fertile_end = _fertile_bounds(calendar, today)

    confirmation = calendar.period_confirmation
    awaiting = bool(confirmation and confirmation.untracked_period_dates)

    return CycleState(
        as_of=today,
        cycle_day=current.cycle_day if current else None,
        phase=phase_of(current, ovulation_day) if current else CyclePhase.UNKNOWN,
        is_predicted=bool(
            current and any(phase.type.is_predicted for phase in current.phases)
        ),
        in_period=bool(current and current.in_period),
        in_fertile_window=bool(current and current.in_fertile_window),
        is_ovulation_day=bool(current and current.is_ovulation),
        period_level=current.period_level if current else None,
        current_period_start=covering.start if covering else None,
        last_period_start=last.start if last else None,
        last_period_end=last.end if last else None,
        last_period_length=last.length if last else None,
        next_period_start=next_period.start if next_period else None,
        next_period_end=next_period.end if next_period else None,
        days_until_next_period=(
            (next_period.start - today).days if next_period else None
        ),
        next_ovulation=next_ovulation,
        days_until_next_ovulation=(
            (next_ovulation - today).days if next_ovulation else None
        ),
        fertile_window_start=fertile_start,
        fertile_window_end=fertile_end,
        tracked_categories=current.category_groups if current else (),
        awaiting_period_confirmation=awaiting,
        calendar_end=calendar.max_calendar_date,
    )
