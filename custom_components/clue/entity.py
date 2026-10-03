"""Base entity for the Clue integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ClueDataUpdateCoordinator


class ClueEntity(CoordinatorEntity[ClueDataUpdateCoordinator]):
    """An entity reading from the Clue coordinator.

    Every entity of one config entry sits on a single service device, named
    after the person whose cycle it tracks.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ClueDataUpdateCoordinator,
        description: EntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.unique_id))},
            name=entry.title,
            manufacturer="Clue",
            model="Cycle tracking" if coordinator.connection_code is None else "Clue Connect",
            entry_type=DeviceEntryType.SERVICE,
        )
