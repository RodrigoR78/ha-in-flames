"""Room temperature sensor."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import InFlamesConfigEntry, InFlamesEntity
from .const import DP_TEMP_CURRENT_C, DP_TEMP_CURRENT_F, DP_UNIT


async def async_setup_entry(
    hass: HomeAssistant, entry: InFlamesConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([InFlamesTemperature(entry.runtime_data)])


class InFlamesTemperature(InFlamesEntity, SensorEntity):
    _attr_translation_key = "room_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, fireplace) -> None:
        super().__init__(fireplace, "room_temperature")

    @property
    def _fahrenheit(self) -> bool:
        return self.fp.dps.get(DP_UNIT, "f") == "f"

    @property
    def native_unit_of_measurement(self) -> str:
        return UnitOfTemperature.FAHRENHEIT if self._fahrenheit else UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> int | None:
        return self.fp.dps.get(DP_TEMP_CURRENT_F if self._fahrenheit else DP_TEMP_CURRENT_C)
