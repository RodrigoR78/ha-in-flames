"""Shut-off timer and sound selection."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import InFlamesConfigEntry, InFlamesEntity
from .const import COUNTDOWNS, DP_SOUND_MODE, DP_TIMER, SOUND_MODES

SELECTS = [
    # (dp, translation key, icon, options)
    (DP_TIMER, "timer", "mdi:timer-outline", COUNTDOWNS),
    (DP_SOUND_MODE, "sound_mode", "mdi:music-note", SOUND_MODES),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: InFlamesConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(InFlamesSelect(entry.runtime_data, *spec) for spec in SELECTS)


class InFlamesSelect(InFlamesEntity, SelectEntity):
    def __init__(self, fireplace, dp: str, key: str, icon: str, options: list[str]) -> None:
        super().__init__(fireplace, key)
        self._dp = dp
        self._attr_translation_key = key
        self._attr_icon = icon
        self._attr_options = options

    @property
    def current_option(self) -> str | None:
        return self.fp.dps.get(self._dp)

    async def async_select_option(self, option: str) -> None:
        await self.fp.set({self._dp: option})
