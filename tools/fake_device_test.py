"""Simulated Tuya v3.4 device, driven by the integration's own client.
usage: python3 fake_device_test.py custom_components/in_flames   (exit 0 = pass)"""
import asyncio, json, struct, sys, hmac, hashlib, os
sys.path.insert(0, sys.argv[1])
import tuya_local as t

KEY = b"0123456789abcdef"
state = {"1": False, "5": "level_1", "8": True, "10": 60, "11": 75, "9": "f"}
got_control = []

async def handle(r, w):
    sk = KEY
    async def send(cmd, payload, key, ret=True):
        body = (b"\0\0\0\0" if ret else b"") + payload
        hdr = t.HEADER.pack(t.PREFIX, 1, cmd, len(body) + 36)
        w.write(hdr + body + t._hmac(key, hdr + body) + struct.pack(">I", t.SUFFIX)); await w.drain()
    async def recv(key):
        hdr = await r.readexactly(16); _, _, cmd, ln = t.HEADER.unpack(hdr)
        body = await r.readexactly(ln); p = body[:-36]
        assert hmac.compare_digest(body[-36:-4], t._hmac(key, hdr + p)), "client HMAC bad"
        return cmd, p
    cmd, p = await recv(KEY); assert cmd == 3
    ln = t._decrypt(KEY, p); rn = b"fedcba9876543210"
    await send(4, t._encrypt(KEY, rn + t._hmac(KEY, ln)), KEY)
    cmd, p = await recv(KEY); assert cmd == 5 and t._decrypt(KEY, p) == t._hmac(KEY, rn), "finish bad"
    sk = t._encrypt(KEY, bytes(a ^ b for a, b in zip(ln, rn)), pad=False)
    while True:
        try: cmd, p = await recv(sk)
        except asyncio.IncompleteReadError: return
        d = t._decrypt(sk, p)
        if cmd == 0x10:
            await send(0x10, t._encrypt(sk, json.dumps({"dps": state}).encode()), sk)
        elif cmd == 0x0d:
            assert d.startswith(b"3.4"); msg = json.loads(d[15:]); got_control.append(msg)
            state.update(msg["data"]["dps"])
            push = t.VERSION_HEADER + json.dumps({"protocol": 4, "t": 1, "data": {"dps": msg["data"]["dps"]}}).encode()
            await send(0x08, t._encrypt(sk, push), sk, ret=False)

async def main():
    srv = await asyncio.start_server(handle, "127.0.0.1", 0); port = srv.sockets[0].getsockname()[1]
    seen = {}; conn = []
    dev = t.TuyaDevice("127.0.0.1", "dev", KEY.decode(), on_dps=seen.update, on_connection=conn.append, port=port)
    dev.start()
    for _ in range(50):
        await asyncio.sleep(0.05)
        if seen: break
    assert seen.get("11") == 75, f"query failed {seen}"
    await dev.set_dps({"1": True, "5": "level_3"}); await asyncio.sleep(0.2)
    assert seen["1"] is True and seen["5"] == "level_3", seen
    print("control msg:", got_control[0])
    # wrong key must fail negotiation
    bad = t.TuyaDevice("127.0.0.1", "dev", "ffffffffffffffff", port=port)
    try: await bad.connect(); raise SystemExit("BAD KEY ACCEPTED")
    except t.TuyaError as e: print("wrong key rejected:", e)
    await dev.stop(); print("connection events:", conn)
    assert conn == [True, False], conn
    # discovery broadcast round trip (encrypted with the public UDP key)
    info = {"ip": "10.0.0.9", "gwId": "dev", "productKey": "p", "version": "3.4"}
    body = b"\0\0\0\0" + t._encrypt(t.DISCOVERY_KEY, json.dumps(info).encode())
    pkt = t.HEADER.pack(t.PREFIX, 0, 0x13, len(body) + 8) + body + b"\0" * 4 + struct.pack(">I", t.SUFFIX)
    assert t.parse_broadcast(pkt) == info, t.parse_broadcast(pkt)
    print("discovery parse ok"); print("OK")
asyncio.run(main())
