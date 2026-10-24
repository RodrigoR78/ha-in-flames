<p align="center"><img src="assets/icon.svg" width="140" alt="In Flames icon"></p>

# In Flames Fireplace (Local Tuya)

A Home Assistant integration that controls a **Tuya Wi-Fi electric fireplace directly over your LAN**, without going through the Tuya cloud.

- **Local push:** a persistent encrypted connection to the fireplace (Tuya protocol 3.4). Changes made from the app, the remote or the buttons appear in Home Assistant instantly.
- **No cloud after setup:** the cloud is only used once, during setup, to read the device's local key. Sign in by scanning a QR code with the Smart Life app, right on the integration page.
- **No extra libraries for control:** the protocol client is a single file that uses only `cryptography`, which ships with Home Assistant.
- **Honest state:** entities update only when the fireplace confirms a change, so the UI never shows a setting the device didn't accept.

## Entities

| Entity | What it does |
|---|---|
| Climate | on/off (heat), target temperature, room temperature, **heat level 1-5** (shown as fan mode) |
| Switch: Flame light | flame effect on/off, with or without heat |
| Switch: Sound | crackling sound on/off |
| Switch: Child lock | locks the buttons on the unit |
| Select: Shut-off timer | Off, 1-6 hours |
| Select: Sound effect | sound 1-3 |
| Sensor: Room temperature | from the fireplace's own sensor |

Temperatures follow the unit set on the fireplace (°F or °C).

## Supported devices

Tuya electric fireplaces (Tuya category `dbl`) using **local protocol 3.4**. Many brands sell these and control them with the **Smart Life** or **Tuya Smart** app.

| Product id | Status |
|---|---|
| `dayp0pur22rp0omx` | tested: every entity verified on the device |
| other `dbl` products | listed as "untested model" during setup; the datapoints may differ (see [Datapoints](#datapoints)) |

## Requirements

- Home Assistant **2026.3** or newer (the integration icon needs 2026.3).
- The fireplace set up in the Smart Life / Tuya Smart app.
- Home Assistant and the fireplace on the same network. Auto-discovery listens for the fireplace's UDP broadcast; across VLANs you can type its IP instead.

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/RodrigoR78/ha-in-flames`, category **Integration**.
2. Install **In Flames Fireplace (Local Tuya)** and restart Home Assistant.

### Manual

Copy `custom_components/in_flames` into your `config/custom_components/` folder and restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → In Flames Fireplace (Local Tuya)**, then choose one of:

### Sign in with the Smart Life app (recommended)

1. **Find your user code:** Smart Life app → **Me** → ⚙ **Settings** → **Account and Security** → **User Code**. Enter it.
2. **Scan the QR code** shown in Home Assistant: in the app tap **+** (top right) → **Scan**, then confirm the login. Press **Submit**.
3. **Pick your fireplace** from the list.
4. The integration finds the fireplace's IP from its LAN broadcast, checks the key with a real encrypted handshake, and creates the device.

Only the device id, IP and local key are saved. The login session is signed out right after the device list is read, and the integration never contacts Tuya again.

### Enter manually

If you already have the IP, device id and 16-character local key (from `tinytuya wizard` or the Tuya IoT developer platform), enter them directly. The key is checked against the device before anything is saved.

### Re-pairing or a new IP

Re-pairing the fireplace in the app gives it a **new local key**. Open the integration → ⋮ → **Reconfigure** and sign in again (or enter the new key). Entities and their history stay as they are.

**Tip:** give the fireplace a DHCP reservation in your router.

## Datapoints

The fireplace firmware doesn't always match the model Tuya's cloud publishes. On the tested product:

| DP | Use | Note |
|---|---|---|
| 1 | power | |
| 2 / 10 | target temp °C / °F | |
| 3 / 11 | room temp °C / °F | |
| 5 | heat level | `level_1` … `level_5` |
| 7 | child lock | |
| 8 | flame light | |
| 9 | unit | `c` / `f` |
| 15 | work state | `heating` |
| 20 / 21 | sound / sound effect | |
| **103** | shut-off timer | the cloud model says DP 13, which the firmware ignores |

Also reported but not mapped yet: 16, 17 (`amber_and_green`), 25, 101 (`red`), 102, 105. 17 and 101 look like flame and ember colours. If your model differs, use `tools/probe.py` to see what your fireplace reports, and open an issue with the output.

## Tools

| Script | Purpose |
|---|---|
| `tools/discover.py` | list Tuya devices broadcasting on your LAN (IP, id, protocol version); no key needed |
| `tools/probe.py` | print a device's full status and send raw datapoint changes, using the integration's own client (key from `$LK`) |
| `tools/fake_device_test.py` | simulated 3.4 device for testing the protocol code (runs in CI) |
| `tools/make_icon.py` | regenerates the brand icons |

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Could not complete the session handshake" | Wrong key (the device was re-paired: use **Reconfigure**), wrong IP, or the device isn't protocol 3.4 (`tools/discover.py` shows the version). |
| The fireplace isn't found automatically | Home Assistant and the fireplace are on different VLANs, or UDP 6666/6667 is blocked. Enter the IP when asked. |
| The QR login says "not confirmed" | Confirm the login in the app before pressing Submit. QR codes expire after a few minutes; a fresh one is shown automatically. |
| A control does nothing | Your model may use a different datapoint. Check with `tools/probe.py`. |

For details, enable debug logging:

```yaml
logger:
  logs:
    custom_components.in_flames: debug
```

## How it works

Tuya protocol 3.4: a three-message key exchange (client nonce → device nonce + HMAC proof → finish) derives a session key from the device's local key. After that, every frame is AES-128-ECB with an HMAC-SHA256. Control is command `0x0D`, status queries `0x10`, the device pushes `0x08` on every change, and a heartbeat (`0x09`) every 10 s keeps the connection alive. See `custom_components/in_flames/tuya_local.py`.

The Smart Life sign-in uses the same QR login and app client as Home Assistant's built-in Tuya integration (`tuya-device-sharing-sdk`).

## Disclaimer

Not affiliated with or endorsed by Tuya or any fireplace manufacturer. Use at your own risk: this controls a heater.

## License

MIT
