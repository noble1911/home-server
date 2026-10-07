"""End-to-end check of the running voice agent's controls (#217).

A fake user joins a fresh room and checks the agent greets, reports its state,
stops when told to, and stays silent with "Read replies aloud" off. No speech,
STT or LLM involved, so it's quick and free. Run after rebuilding the agent:

    docker exec livekit-agent python e2e_check.py
"""
import asyncio, json, os, time, uuid
from livekit import api, rtc

URL, KEY, SECRET = os.environ["LIVEKIT_URL"], os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"]


def token(room, attrs):
    grants = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True,
                             can_publish_data=True, can_update_own_metadata=True)
    return (api.AccessToken(KEY, SECRET).with_identity("e2e-user").with_name("e2e")
            .with_grants(grants).with_attributes(attrs).to_jwt())


async def run(name, attrs, scenario):
    room_name = f"butler_e2etest_{uuid.uuid4().hex[:8]}"
    room, states = rtc.Room(), []
    t0 = time.monotonic()

    @room.on("data_received")
    def _(pkt):
        try:
            m = json.loads(pkt.data)
        except ValueError:
            return
        if m.get("type") == "agent_state":
            states.append((round(time.monotonic() - t0, 2), m["state"]))

    async def wait_for(state, timeout):
        end = time.monotonic() + timeout
        n = len([s for s in states if s[1] == state])
        while time.monotonic() < end:
            hits = [s for s in states if s[1] == state]
            if len(hits) > n or (n == 0 and hits):
                return hits[-1][0]
            await asyncio.sleep(0.02)
        return None

    await room.connect(URL, token(room_name, attrs))
    try:
        result = await scenario(room, wait_for)
    finally:
        await room.disconnect()
        lk = api.LiveKitAPI(URL.replace("ws://", "http://"), KEY, SECRET)
        try:
            await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
        finally:
            await lk.aclose()
    print(f"{name}: {result} | states {states}")
    return result, states


async def greeting(room, wait_for):
    spk = await wait_for("speaking", 25)
    idle = await wait_for("idle", 15)
    return {"speaking_at": spk, "idle_at": idle, "spoke_for": idle and spk and round(idle - spk, 2)}


async def stop_button(room, wait_for):
    spk = await wait_for("speaking", 25)
    if spk is None:
        return {"error": "never spoke"}
    sent = time.monotonic()
    await room.local_participant.publish_data(json.dumps({"type": "interrupt"}).encode(),
                                              reliable=True, topic="butler-control")
    idle = await wait_for("idle", 15)
    return {"stopped_after": idle and round(time.monotonic() - sent, 2)}


async def read_aloud_off(room, wait_for):
    return {"spoke": await wait_for("speaking", 10)}


async def toggle_off_mid_reply(room, wait_for):
    spk = await wait_for("speaking", 25)
    if spk is None:
        return {"error": "never spoke"}
    sent = time.monotonic()
    await room.local_participant.set_attributes({"speak_replies": "false"})
    idle = await wait_for("idle", 15)
    return {"stopped_after": idle and round(time.monotonic() - sent, 2)}


async def main():
    ok = True
    (g, _) = await run("greeting", {"speak_replies": "true"}, greeting)
    ok &= bool(g["spoke_for"])
    (s, _) = await run("stop button", {"speak_replies": "true"}, stop_button)
    ok &= bool(s.get("stopped_after") is not None and g["spoke_for"] and s["stopped_after"] < g["spoke_for"])
    (r, _) = await run("read aloud off", {"speak_replies": "false"}, read_aloud_off)
    ok &= r["spoke"] is None
    (t, _) = await run("toggle off mid-reply", {"speak_replies": "true"}, toggle_off_mid_reply)
    ok &= bool(t.get("stopped_after") is not None and t["stopped_after"] < g["spoke_for"])
    print("E2E PASSED" if ok else "E2E FAILED")

asyncio.run(main())
