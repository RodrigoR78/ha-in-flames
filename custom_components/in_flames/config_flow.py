"""Config flow.

Two ways in, both ending with a live handshake against the device before anything is saved:
  * Smart Life sign-in: user code -> scan a QR in the app -> pick the fireplace -> its LAN
    address is found from the device's own broadcast. Fetches the local key for you.
  * Manual: IP, device id and local key you already have.
Reconfigure (integration page -> ... -> Reconfigure) offers the same two paths, e.g. to
pick up a new local key after the fireplace was re-paired in the app.
"""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers import selector

from .const import CONF_DEVICE_ID, CONF_LOCAL_KEY, DOMAIN, FIREPLACE_CATEGORY, TESTED_PRODUCTS
from .tuya_local import TuyaDevice, TuyaError, discover

CONF_USER_CODE = "user_code"
CONF_DEVICE = "device"
USER_CODE_HELP = "Smart Life app → Me → ⚙ Settings → Account and Security → User Code"


async def _validate(host: str, device_id: str, local_key: str) -> dict[str, Any]:
    """Connect, negotiate and wait for the first DP report."""
    got: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()

    def on_dps(dps: dict[str, Any]) -> None:
        if not got.done():
            got.set_result(dps)

    dev = TuyaDevice(host, device_id, local_key, on_dps=on_dps)
    dev.start()
    try:
        return await asyncio.wait_for(got, 15)
    finally:
        await dev.stop()


def _qr_schema(qr: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional("qr"): selector.QrCodeSelector(
                selector.QrCodeSelectorConfig(
                    data=qr, scale=5, error_correction_level=selector.QrErrorCorrectionLevel.QUARTILE
                )
            )
        }
    )


class InFlamesConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._login = None
        self._qr = ""
        self._devices: dict = {}
        self._device = None

    # ---- entry points ----------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["cloud", "manual"])

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="reconfigure", menu_options=["cloud", "manual"])

    # ---- Smart Life sign-in ----------------------------------------------

    async def async_step_cloud(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        from .cloud import CloudError, SmartLifeLogin  # imports the Tuya SDK only when used

        errors: dict[str, str] = {}
        placeholders = {"where": USER_CODE_HELP, "error": ""}
        if user_input is not None:
            self._login = SmartLifeLogin(user_input[CONF_USER_CODE])
            try:
                self._qr = await self.hass.async_add_executor_job(self._login.request_qr)
            except (CloudError, OSError) as err:
                errors["base"] = "cloud_error"
                placeholders["error"] = str(err)
            else:
                return await self.async_step_scan()
        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema({vol.Required(CONF_USER_CODE): str}),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_scan(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        from .cloud import CloudError

        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            try:
                devices = await self.hass.async_add_executor_job(self._login.fetch_devices)
            except (CloudError, OSError) as err:
                errors["base"] = "scan_failed"
                placeholders["error"] = str(err)
                try:  # QR tokens are single-use and short-lived; offer a fresh one
                    self._qr = await self.hass.async_add_executor_job(self._login.request_qr)
                except (CloudError, OSError):
                    pass
            else:
                self._devices = {d.id: d for d in devices if d.category == FIREPLACE_CATEGORY and d.local_key}
                if not self._devices:
                    return self.async_abort(
                        reason="no_fireplaces", description_placeholders={"count": str(len(devices))}
                    )
                return await self.async_step_pick()
        return self.async_show_form(
            step_id="scan", data_schema=_qr_schema(self._qr), errors=errors, description_placeholders=placeholders
        )

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._device = self._devices[user_input[CONF_DEVICE]]
            return await self.async_step_locate()
        options = [
            selector.SelectOptionDict(
                value=d.id,
                label=f"{d.name} - {d.product_name or d.product_id}"
                + (" (tested)" if d.product_id in TESTED_PRODUCTS else " (untested model)")
                + (f" · {d.home}" if d.home else ""),
            )
            for d in self._devices.values()
        ]
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE, default=options[0]["value"]): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.LIST)
                    )
                }
            ),
        )

    async def async_step_locate(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Find the device's LAN address from its broadcast; ask for it if that fails."""
        errors: dict[str, str] = {}
        host = None
        if user_input is not None:
            host = user_input[CONF_HOST]
        else:
            found = await discover(8, self._device.id)
            if self._device.id in found:
                host = found[self._device.id]["ip"]
                version = found[self._device.id].get("version")
                if version and version != "3.4":
                    return self.async_abort(reason="unsupported_version", description_placeholders={"version": version})
        if host:
            data = {CONF_HOST: host, CONF_DEVICE_ID: self._device.id, CONF_LOCAL_KEY: self._device.local_key}
            result = await self._finish(data, title=self._device.name)
            if result:
                return result
            errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="locate",
            data_schema=vol.Schema({vol.Required(CONF_HOST, default=host or ""): str}),
            errors=errors,
            description_placeholders={"name": self._device.name},
        )

    # ---- manual ------------------------------------------------------------

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = self._get_reconfigure_entry().data if self.source == SOURCE_RECONFIGURE else {}
        if user_input is not None:
            if len(user_input[CONF_LOCAL_KEY]) != 16:
                errors[CONF_LOCAL_KEY] = "invalid_key"
            else:
                result = await self._finish(user_input, title="In Flames")
                if result:
                    return result
                errors["base"] = "cannot_connect"
        defaults = user_input or current
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
                    vol.Required(CONF_DEVICE_ID, default=defaults.get(CONF_DEVICE_ID, "")): str,
                    vol.Required(CONF_LOCAL_KEY): str,
                }
            ),
            errors=errors,
        )

    # ---- common ------------------------------------------------------------

    async def _finish(self, data: dict[str, Any], title: str) -> ConfigFlowResult | None:
        """Validate against the device, then create or update the entry. None = can't connect."""
        await self.async_set_unique_id(data[CONF_DEVICE_ID])
        if self.source == SOURCE_RECONFIGURE:
            self._abort_if_unique_id_mismatch(reason="wrong_device")
        try:
            await _validate(data[CONF_HOST], data[CONF_DEVICE_ID], data[CONF_LOCAL_KEY])
        except (TimeoutError, OSError, TuyaError):
            return None
        if self.source == SOURCE_RECONFIGURE:
            return self.async_update_reload_and_abort(self._get_reconfigure_entry(), data_updates=data)
        self._abort_if_unique_id_configured(updates=data)
        return self.async_create_entry(title=title, data=data)
