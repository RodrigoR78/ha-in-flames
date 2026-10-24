"""In Flames fireplace - local Tuya v3.4 control, no cloud."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CONF_DEVICE_ID, CONF_LOCAL_KEY, DOMAIN
from .tuya_local import TuyaDevice

PLATFORMS = [Platform.CLIMATE, Platform.SELECT, Platform.SENSOR, Platform.SWITCH]

type InFlamesConfigEntry = ConfigEntry[InFlames]


class InFlames:
    """Holds the connection and the latest DP values, fans updates out to entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.device_id: str = entry.data[CONF_DEVICE_ID]
        self.dps: dict[str, Any] = {}
        self._listeners: list[Callable[[], None]] = []
        self.client = TuyaDevice(
            entry.data[CONF_HOST],
            self.device_id,
            entry.data[CONF_LOCAL_KEY],
            on_dps=self._on_dps,
            on_connection=lambda _up: self._notify(),
        )

    @property
    def available(self) -> bool:
        return self.client.connected and bool(self.dps)

    @callback
    def _on_dps(self, dps: dict[str, Any]) -> None:
        self.dps.update(dps)
        self._notify()

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    async def set(self, dps: dict[str, Any]) -> None:
        await self.client.set_dps(dps)


async def async_setup_entry(hass: HomeAssistant, entry: InFlamesConfigEntry) -> bool:
    fireplace = InFlames(hass, entry)
    fireplace.client.start()
    entry.runtime_data = fireplace
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: InFlamesConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.stop()
    return unloaded


class InFlamesEntity(Entity):
    """Base entity: push-updated from the shared InFlames object."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, fireplace: InFlames, key: str) -> None:
        self.fp = fireplace
        self._attr_unique_id = f"{fireplace.device_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, fireplace.device_id)},
            name="In Flames",
            manufacturer="Tuya",
            model="Electric fireplace (dayp0pur22rp0omx)",
        )

    @property
    def available(self) -> bool:
        return self.fp.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.fp.add_listener(self.async_write_ha_state))
