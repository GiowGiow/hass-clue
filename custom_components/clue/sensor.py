"""Sensors for the Clue integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClueConfigEntry
from .entity import ClueEntity
from .pyclue import CyclePhase, CycleState


@dataclass(frozen=True, kw_only=True)
class ClueSensorEntityDescription(SensorEntityDescription):
    """Describes a Clue sensor."""

    value_fn: Callable[[CycleState], str | int | date | None]


SENSORS: tuple[ClueSensorEntityDescription, ...] = (
    ClueSensorEntityDescription(
        key="cycle_day",
        translation_key="cycle_day",
        value_fn=lambda state: state.cycle_day,
    ),
    ClueSensorEntityDescription(
        key="phase",
        translation_key="phase",
        device_class=SensorDeviceClass.ENUM,
        options=[phase.value for phase in CyclePhase],
        value_fn=lambda state: state.phase.value,
    ),
    ClueSensorEntityDescription(
        key="next_period",
        translation_key="next_period",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda state: state.next_period_start,
    ),
    ClueSensorEntityDescription(
        key="days_until_next_period",
        translation_key="days_until_next_period",
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda state: state.days_until_next_period,
    ),
    ClueSensorEntityDescription(
        key="last_period_start",
        translation_key="last_period_start",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda state: state.last_period_start,
    ),
    ClueSensorEntityDescription(
        key="last_period_length",
        translation_key="last_period_length",
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda state: state.last_period_length,
    ),
    ClueSensorEntityDescription(
        key="next_ovulation",
        translation_key="next_ovulation",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda state: state.next_ovulation,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClueConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Clue sensors."""
    coordinator = entry.runtime_data
    async_add_entities(ClueSensor(coordinator, description) for description in SENSORS)


class ClueSensor(ClueEntity, SensorEntity):
    """A sensor reporting one field of the derived cycle state."""

    entity_description: ClueSensorEntityDescription

    @property
    def native_value(self) -> str | int | date | None:
        return self.entity_description.value_fn(self.coordinator.data)
