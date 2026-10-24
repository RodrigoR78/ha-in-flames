"""One-shot Tuya cloud helper for the config flow: Smart Life QR login, then list the
account's devices with their local keys, then sign the session out again.

Uses the same "Smart Life / Home Assistant" login as Home Assistant's own Tuya
integration (tuya-device-sharing-sdk). Nothing from the cloud is stored except the
chosen device's id and local key; after setup the integration never talks to Tuya.
These calls block, so run them in the executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tuya_sharing import CustomerApi, LoginControl
from tuya_sharing.customerapi import CustomerTokenInfo

# Home Assistant's registered Smart Life client, as used by the core Tuya integration.
TUYA_CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
TUYA_SCHEMA = "haauthorize"
QR_PREFIX = "tuyaSmart--qrLogin?token="


class CloudError(Exception):
    """Tuya refused a request; str() is the message to show."""


@dataclass
class CloudDevice:
    id: str
    name: str
    local_key: str
    category: str
    product_id: str
    product_name: str
    home: str


class SmartLifeLogin:
    def __init__(self, user_code: str) -> None:
        self.user_code = user_code.strip()
        self._login = LoginControl()
        self.qr_token: str | None = None

    def request_qr(self) -> str:
        """Ask Tuya for a login QR; returns the string to encode in the QR code."""
        resp = self._login.qr_code(TUYA_CLIENT_ID, TUYA_SCHEMA, self.user_code)
        if not resp.get("success"):
            raise CloudError(f"{resp.get('msg', 'unknown error')} (code {resp.get('code', '?')})")
        self.qr_token = resp["result"]["qrcode"]
        return QR_PREFIX + self.qr_token

    def fetch_devices(self) -> list[CloudDevice]:
        """After the QR was scanned and confirmed in the app: list devices, then log out."""
        ok, info = self._login.login_result(self.qr_token, TUYA_CLIENT_ID, self.user_code)
        if not ok:
            raise CloudError(f"{info.get('msg', 'login not confirmed yet')} (code {info.get('code', '?')})")
        api = CustomerApi(
            CustomerTokenInfo(
                {k: info[k] for k in ("t", "uid", "expire_time", "access_token", "refresh_token")}
            ),
            TUYA_CLIENT_ID,
            self.user_code,
            info["endpoint"],
            None,
        )
        try:
            return self._devices(api)
        finally:
            try:  # end this one-off session (it's ours alone; other logins are untouched)
                api.post(
                    "/v1.0/m/token/terminal/expire",
                    None,
                    {"accessToken": api.token_info.access_token, "terminalId": info["terminal_id"]},
                )
            except Exception:  # noqa: BLE001 - best effort, the token expires in 2 h anyway
                pass

    @staticmethod
    def _devices(api: CustomerApi) -> list[CloudDevice]:
        homes = _result(api.get("/v1.0/m/life/users/homes"))
        devices: list[CloudDevice] = []
        for home in homes:
            for d in _result(api.get("/v1.0/m/life/ha/home/devices", {"homeId": home["ownerId"]})):
                devices.append(
                    CloudDevice(
                        id=d["id"],
                        name=d.get("name") or d["id"],
                        local_key=d.get("local_key", ""),
                        category=d.get("category", ""),
                        product_id=d.get("product_id", ""),
                        product_name=d.get("product_name", ""),
                        home=home.get("name", ""),
                    )
                )
        return devices


def _result(resp: dict[str, Any]) -> list[dict[str, Any]]:
    if not resp.get("success"):
        raise CloudError(f"{resp.get('msg', 'unknown error')} (code {resp.get('code', '?')})")
    return resp.get("result") or []
