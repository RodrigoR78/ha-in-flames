"""Flame light, child lock and sound switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import InFlamesConfigEntry, InFlamesEntity
from .const import DP_CHILD_LOCK, DP_LIGHT, DP_SOUND

SWITCHES = [
    # (dp, translation key, icon, category)
    (DP_LIGHT, "flame_light", "mdi:fire", None),
    (DP_SOUND, "sound", "mdi:volume-high", None),
    (DP_CHILD_LOCK, "child_lock", "mdi:lock", EntityCategory.CONFIG),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: InFlamesConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(InFlamesSwitch(entry.runtime_data, *spec) for spec in SWITCHES)


class InFlamesSwitch(InFlamesEntity, SwitchEntity):
    def __init__(self, fireplace, dp: str, key: str, icon: str, category) -> None:
        super().__init__(fireplace, key)
        self._dp = dp
        self._attr_translation_key = key
        self._attr_icon = icon
        self._attr_entity_category = category

    @property
    def is_on(self) -> bool | None:
        return self.fp.dps.get(self._dp)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.fp.set({self._dp: True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.fp.set({self._dp: False})
