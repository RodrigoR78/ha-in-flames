"""Fireplace heater as a climate entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import InFlamesConfigEntry, InFlamesEntity
from .const import (
    DP_LEVEL,
    DP_POWER,
    DP_TEMP_CURRENT_C,
    DP_TEMP_CURRENT_F,
    DP_TEMP_SET_C,
    DP_TEMP_SET_F,
    DP_UNIT,
    DP_WORK_STATE,
    LEVELS,
    TEMP_RANGE_C,
    TEMP_RANGE_F,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: InFlamesConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([InFlamesClimate(entry.runtime_data)])


class InFlamesClimate(InFlamesEntity, ClimateEntity):
    """On/off, target temperature and heat level (exposed as fan modes, like the Tuya integration did)."""

    _attr_name = None
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_fan_modes = LEVELS
    _attr_target_temperature_step = 1
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_translation_key = "fireplace"

    def __init__(self, fireplace) -> None:
        super().__init__(fireplace, "climate")

    @property
    def _fahrenheit(self) -> bool:
        return self.fp.dps.get(DP_UNIT, "f") == "f"

    @property
    def temperature_unit(self) -> str:
        return UnitOfTemperature.FAHRENHEIT if self._fahrenheit else UnitOfTemperature.CELSIUS

    @property
    def min_temp(self) -> float:
        return (TEMP_RANGE_F if self._fahrenheit else TEMP_RANGE_C)[0]

    @property
    def max_temp(self) -> float:
        return (TEMP_RANGE_F if self._fahrenheit else TEMP_RANGE_C)[1]

    @property
    def current_temperature(self) -> float | None:
        return self.fp.dps.get(DP_TEMP_CURRENT_F if self._fahrenheit else DP_TEMP_CURRENT_C)

    @property
    def target_temperature(self) -> float | None:
        return self.fp.dps.get(DP_TEMP_SET_F if self._fahrenheit else DP_TEMP_SET_C)

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self.fp.dps.get(DP_POWER) else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        if not self.fp.dps.get(DP_POWER):
            return HVACAction.OFF
        return HVACAction.HEATING if self.fp.dps.get(DP_WORK_STATE) == "heating" else HVACAction.IDLE

    @property
    def fan_mode(self) -> str | None:
        return self.fp.dps.get(DP_LEVEL)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.fp.set({DP_POWER: hvac_mode == HVACMode.HEAT})

    async def async_turn_on(self) -> None:
        await self.fp.set({DP_POWER: True})

    async def async_turn_off(self) -> None:
        await self.fp.set({DP_POWER: False})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        dp = DP_TEMP_SET_F if self._fahrenheit else DP_TEMP_SET_C
        await self.fp.set({dp: int(round(temp))})

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.fp.set({DP_LEVEL: fan_mode})
