"""Minimal asyncio client for the Tuya local LAN protocol, version 3.4.

Only what the In Flames fireplace needs: session-key negotiation, DP query,
DP control, heartbeat and pushed status updates.

Frame layout (both directions):
    prefix 0x000055AA | seq | cmd | length | [retcode] | payload | HMAC-SHA256 | suffix 0x0000AA55
`length` counts everything after itself. Device->client frames may carry a
4-byte return code before the encrypted payload.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import struct
import time
from collections.abc import Callable
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

PREFIX = 0x000055AA
SUFFIX = 0x0000AA55
HEADER = struct.Struct(">4I")

CMD_SESS_KEY_NEG_START = 0x03
CMD_SESS_KEY_NEG_RESP = 0x04
CMD_SESS_KEY_NEG_FINISH = 0x05
CMD_STATUS = 0x08
CMD_HEART_BEAT = 0x09
CMD_CONTROL_NEW = 0x0D
CMD_DP_QUERY_NEW = 0x10
CMD_UPDATEDPS = 0x12

VERSION_HEADER = b"3.4" + b"\x00" * 12
HEARTBEAT_INTERVAL = 10
CONNECT_TIMEOUT = 5
READ_TIMEOUT = HEARTBEAT_INTERVAL * 3


DISCOVERY_PORTS = (6666, 6667)
DISCOVERY_KEY = hashlib.md5(b"yGAdlopoPVldABfn").digest()  # public, same for every device


class TuyaError(Exception):
    """Protocol or connection failure."""


def _encrypt(key: bytes, data: bytes, pad: bool = True) -> bytes:
    if pad:
        n = 16 - len(data) % 16
        data += bytes([n]) * n
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return enc.update(data) + enc.finalize()


def _decrypt(key: bytes, data: bytes) -> bytes:
    dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    out = dec.update(data) + dec.finalize()
    n = out[-1] if out else 0
    if 0 < n <= 16 and out.endswith(bytes([n]) * n):
        out = out[:-n]
    return out


def _hmac(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def _json(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode()


def parse_broadcast(data: bytes) -> dict[str, Any] | None:
    """Decode a LAN discovery broadcast: {"ip", "gwId", "productKey", "version", ...}."""
    payload = data[20:-8]  # header + retcode, then crc + suffix
    for candidate in (lambda: _decrypt(DISCOVERY_KEY, payload), lambda: payload):
        try:
            return json.loads(candidate())
        except (ValueError, UnicodeDecodeError):
            continue
    return None


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, found: dict[str, dict[str, Any]], wanted: str | None, done: asyncio.Event) -> None:
        self.found, self.wanted, self.done = found, wanted, done

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        info = parse_broadcast(data)
        if not info or not info.get("gwId"):
            return
        info.setdefault("ip", addr[0])
        self.found[info["gwId"]] = info
        if self.wanted and info["gwId"] == self.wanted:
            self.done.set()


async def discover(timeout: float = 8, device_id: str | None = None) -> dict[str, dict[str, Any]]:
    """Listen for device broadcasts; returns {device_id: info}. Stops early once device_id is seen."""
    loop = asyncio.get_running_loop()
    found: dict[str, dict[str, Any]] = {}
    done = asyncio.Event()
    transports = []
    for port in DISCOVERY_PORTS:
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _DiscoveryProtocol(found, device_id, done),
                local_addr=("0.0.0.0", port),
                reuse_port=True,
            )
            transports.append(transport)
        except OSError as err:
            _LOGGER.debug("Cannot listen on UDP %s: %s", port, err)
    if not transports:
        return found
    try:
        await asyncio.wait_for(done.wait(), timeout)
    except TimeoutError:
        pass
    finally:
        for transport in transports:
            transport.close()
    return found


class TuyaDevice:
    """Persistent connection to one Tuya v3.4 device."""

    def __init__(
        self,
        host: str,
        device_id: str,
        local_key: str,
        on_dps: Callable[[dict[str, Any]], None] | None = None,
        on_connection: Callable[[bool], None] | None = None,
        port: int = 6668,
    ) -> None:
        self.host = host
        self.port = port
        self.device_id = device_id
        self._local_key = local_key.encode("latin1")
        self._session_key = self._local_key
        self._on_dps = on_dps
        self._on_connection = on_connection
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._write_lock = asyncio.Lock()
        self._seq = 0
        self._task: asyncio.Task | None = None
        self._stopping = False
        self.connected = False

    # ---- lifecycle -------------------------------------------------------

    def start(self) -> None:
        """Run the connect/read/reconnect loop in the background."""
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name=f"in_flames {self.host}")

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._close()

    async def _run(self) -> None:
        backoff = 5
        while not self._stopping:
            try:
                await self.connect()
                backoff = 5
                await self.query()
                await self._read_loop()
            except asyncio.CancelledError:
                raise
            except (OSError, TuyaError, asyncio.TimeoutError) as err:
                _LOGGER.debug("Connection to %s lost: %s", self.host, err)
            await self._close()
            if self._stopping:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def _close(self) -> None:
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
        self._reader = self._writer = None
        if self.connected:
            self.connected = False
            if self._on_connection:
                self._on_connection(False)

    # ---- connection ------------------------------------------------------

    async def connect(self) -> None:
        """Open the socket and negotiate a session key."""
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT
        )
        self._session_key = self._local_key
        lk = self._local_key

        local_nonce = secrets.token_hex(8).encode()
        await self._send(CMD_SESS_KEY_NEG_START, _encrypt(lk, local_nonce), hmac_key=lk)
        cmd, payload = await asyncio.wait_for(self._read_frame(hmac_key=lk), CONNECT_TIMEOUT)
        if cmd != CMD_SESS_KEY_NEG_RESP:
            raise TuyaError(f"unexpected negotiation reply cmd {cmd:#x}")
        resp = _decrypt(lk, payload)
        remote_nonce, proof = resp[:16], resp[16:48]
        if not hmac.compare_digest(proof, _hmac(lk, local_nonce)):
            raise TuyaError("session negotiation failed (wrong local key?)")
        await self._send(
            CMD_SESS_KEY_NEG_FINISH, _encrypt(lk, _hmac(lk, remote_nonce)), hmac_key=lk
        )
        mixed = bytes(a ^ b for a, b in zip(local_nonce, remote_nonce))
        self._session_key = _encrypt(lk, mixed, pad=False)

        self.connected = True
        if self._on_connection:
            self._on_connection(True)

    # ---- framing ---------------------------------------------------------

    async def _send(self, cmd: int, payload: bytes, hmac_key: bytes | None = None) -> None:
        if not self._writer:
            raise TuyaError("not connected")
        async with self._write_lock:
            self._seq += 1
            header = HEADER.pack(PREFIX, self._seq, cmd, len(payload) + 36)
            mac = _hmac(hmac_key or self._session_key, header + payload)
            self._writer.write(header + payload + mac + struct.pack(">I", SUFFIX))
            await self._writer.drain()

    async def _read_frame(self, hmac_key: bytes | None = None) -> tuple[int, bytes]:
        assert self._reader
        try:
            header = await self._reader.readexactly(HEADER.size)
            prefix, _seq, cmd, length = HEADER.unpack(header)
            if prefix != PREFIX or not 36 <= length <= 65536:
                raise TuyaError("bad frame header")
            body = await self._reader.readexactly(length)
        except asyncio.IncompleteReadError as err:
            raise TuyaError("device closed the connection") from err
        payload, mac, suffix = body[:-36], body[-36:-4], body[-4:]
        if struct.unpack(">I", suffix)[0] != SUFFIX:
            raise TuyaError("bad frame suffix")
        if not hmac.compare_digest(mac, _hmac(hmac_key or self._session_key, header + payload)):
            raise TuyaError("frame HMAC mismatch")
        if len(payload) % 16 == 4:  # leading return code
            payload = payload[4:]
        return cmd, payload

    async def _read_loop(self) -> None:
        last_beat = time.monotonic()
        while True:
            wait = max(0.1, HEARTBEAT_INTERVAL - (time.monotonic() - last_beat))
            try:
                cmd, payload = await asyncio.wait_for(self._read_frame(), wait)
            except asyncio.TimeoutError:
                await self._send_json(
                    CMD_HEART_BEAT, {"gwId": self.device_id, "devId": self.device_id}
                )
                last_beat = time.monotonic()
                continue
            self._handle(cmd, payload)

    def _handle(self, cmd: int, payload: bytes) -> None:
        if not payload:
            return
        data = _decrypt(self._session_key, payload)
        if data.startswith(b"3.4"):
            data = data[len(VERSION_HEADER):]
        if not data or cmd == CMD_HEART_BEAT:
            return
        try:
            msg = json.loads(data)
        except ValueError:
            _LOGGER.debug("Ignoring non-JSON payload for cmd %#x: %r", cmd, data[:64])
            return
        dps = msg.get("dps") or (msg.get("data") or {}).get("dps")
        if dps and self._on_dps:
            self._on_dps(dps)

    # ---- commands --------------------------------------------------------

    async def _send_json(self, cmd: int, obj: Any, version_header: bool = False) -> None:
        raw = _json(obj)
        if version_header:
            raw = VERSION_HEADER + raw
        await self._send(cmd, _encrypt(self._session_key, raw))

    async def query(self) -> None:
        """Ask the device for all DPs; the reply arrives through on_dps."""
        t = str(int(time.time()))
        await self._send_json(
            CMD_DP_QUERY_NEW,
            {"gwId": self.device_id, "devId": self.device_id, "uid": self.device_id, "t": t},
        )

    async def refresh(self, dps: list[int]) -> None:
        """Ask the device to re-report specific (sensor) DPs."""
        await self._send_json(CMD_UPDATEDPS, {"dpId": dps})

    async def set_dps(self, dps: dict[str, Any]) -> None:
        await self._send_json(
            CMD_CONTROL_NEW,
            {"protocol": 5, "t": int(time.time()), "data": {"dps": dps}},
            version_header=True,
        )
