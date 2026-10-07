"""Mock of Butler's /api/notifications/ws, for testing the Android notification service.

Usage: python mock-notify-server.py PORT [START_ID] [DROP_AFTER_SECONDS]
See docs/18-android-app.md (Testing). Needs: pip install websockets
"""
import asyncio, json, sys
from urllib.parse import parse_qs, urlparse
import websockets

TOKEN = "test-token"
next_id = {"n": int(sys.argv[2]) if len(sys.argv) > 2 else 5}
DROP_AFTER = float(sys.argv[3]) if len(sys.argv) > 3 else 0


async def handler(ws):
    path = ws.request.path
    auth = ws.request.headers.get("Authorization", "")
    since = int(parse_qs(urlparse(path).query).get("since", ["0"])[0])
    print(f"CONNECT path={path} auth_ok={auth == 'Device ' + TOKEN} since={since}", flush=True)
    if auth != "Device " + TOKEN:
        await ws.close(4401)
        return
    for title, cat, silent in [("Bins tonight", "reminder", False), ("Send email to Sam?", "approval", False), ("Quiet one", "general", True)]:
        next_id["n"] += 1
        await ws.send(json.dumps({"type": "notification", "id": next_id["n"], "title": title,
                                  "body": f"{title} (id {next_id['n']})", "url": "/", "category": cat,
                                  "silent": silent, "createdAt": "2026-10-07T16:30:00+01:00"}))
        print(f"SENT id={next_id['n']} {cat}", flush=True)
    try:
        if DROP_AFTER:
            await asyncio.sleep(DROP_AFTER)
            print("DROPPING connection to test reconnect", flush=True)
            await ws.close(1012)
            return
        async for msg in ws:
            print("RECV", msg, flush=True)
    except websockets.ConnectionClosed:
        pass
    print("CLOSED", flush=True)


async def main():
    port = int(sys.argv[1])
    async with websockets.serve(handler, "0.0.0.0", port, ping_interval=None):
        print(f"listening on {port}", flush=True)
        await asyncio.Future()

asyncio.run(main())
