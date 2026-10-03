"""Binary sensors for the Clue integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClueConfigEntry
from .entity import ClueEntity
from .pyclue import CycleState


@dataclass(frozen=True, kw_only=True)
class ClueBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Clue binary sensor."""

    is_on_fn: Callable[[CycleState], bool]
    attributes_fn: Callable[[CycleState], dict[str, Any]] | None = None


def _fertile_window_attributes(state: CycleState) -> dict[str, Any]:
    return {
        "window_start": state.fertile_window_start,
        "window_end": state.fertile_window_end,
    }


BINARY_SENSORS: tuple[ClueBinarySensorEntityDescription, ...] = (
    ClueBinarySensorEntityDescription(
        key="period",
        translation_key="period",
        is_on_fn=lambda state: state.in_period,
    ),
    ClueBinarySensorEntityDescription(
        key="fertile_window",
        translation_key="fertile_window",
        is_on_fn=lambda state: state.in_fertile_window,
        attributes_fn=_fertile_window_attributes,
    ),
    ClueBinarySensorEntityDescription(
        key="ovulation_day",
        translation_key="ovulation_day",
        is_on_fn=lambda state: state.is_ovulation_day,
    ),
    ClueBinarySensorEntityDescription(
        key="awaiting_period_confirmation",
        translation_key="awaiting_period_confirmation",
        entity_registry_enabled_default=False,
        is_on_fn=lambda state: state.awaiting_period_confirmation,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClueConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Clue binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        ClueBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class ClueBinarySensor(ClueEntity, BinarySensorEntity):
    """A binary sensor reporting one flag of the derived cycle state."""

    entity_description: ClueBinarySensorEntityDescription

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
