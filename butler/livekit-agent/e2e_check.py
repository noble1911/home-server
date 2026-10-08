"""End-to-end check of the running voice agent (#217, #219).

A fake user joins a fresh room and checks the agent joins and reports its
state, doesn't talk unprompted (no greeting over the user), and handles a
push-to-talk press with nothing said without replying. No speech, so nothing
reaches STT or Claude: quick and free. Run after rebuilding the agent:

    docker exec livekit-agent python e2e_check.py

For the full browser -> agent check with real speech, see harness/README.md.
"""
import asyncio, json, os, time, uuid
from livekit import api, rtc

URL, KEY, SECRET = os.environ["LIVEKIT_URL"], os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"]
AGENT_READY_TIMEOUT = 15


def token(room):
    grants = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True,
                             can_publish_data=True, can_update_own_metadata=True)
    return (api.AccessToken(KEY, SECRET).with_identity("e2e-user").with_name("e2e")
            .with_grants(grants).with_attributes({"speak_replies": "true"}).to_jwt())


async def main():
    room_name = f"butler_e2etest_{uuid.uuid4().hex[:8]}"
    room, states, t0 = rtc.Room(), [], time.monotonic()
    ready = asyncio.Event()

    @room.on("data_received")
    def _(pkt):
        try:
            m = json.loads(pkt.data)
        except ValueError:
            return
        if m.get("type") == "agent_state":
            states.append((round(time.monotonic() - t0, 2), m["state"]))

    def check_ready(*_):
        for p in room.remote_participants.values():
            if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT and p.attributes.get("lk.agent.state"):
                ready.set()
    room.on("participant_attributes_changed", check_ready)
    room.on("participant_connected", check_ready)

    results = {}
    await room.connect(URL, token(room_name))
    try:
        check_ready()
        try:
            await asyncio.wait_for(ready.wait(), AGENT_READY_TIMEOUT)
            results["joined_in_s"] = round(time.monotonic() - t0, 2)
        except asyncio.TimeoutError:
            results["joined_in_s"] = None

        # No greeting: Butler shouldn't talk over someone who's just pressed the mic
        await asyncio.sleep(3)
        results["spoke_unprompted"] = any(s == "speaking" for _, s in states)

        # Push-to-talk with nothing said: press (unmute) then let go (mute); no reply expected
        source = rtc.AudioSource(48000, 1)
        mic = rtc.LocalAudioTrack.create_audio_track("mic", source)
        await room.local_participant.publish_track(
            mic, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        mic.mute()
        await asyncio.sleep(1)
        before = len(states)
        mic.unmute()
        await asyncio.sleep(1.5)
        mic.mute()
        await asyncio.sleep(4)
        results["replied_to_silence"] = any(s in ("thinking", "speaking") for _, s in states[before:])
        results["agent_still_there"] = any(
            p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT for p in room.remote_participants.values())
    finally:
        await room.disconnect()
        lk = api.LiveKitAPI(URL.replace("ws://", "http://"), KEY, SECRET)
        try:
            await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
        finally:
            await lk.aclose()

    print(f"{results} | states {states}")
    ok = (results["joined_in_s"] is not None and not results["spoke_unprompted"]
          and not results["replied_to_silence"] and results["agent_still_there"])
    print("E2E PASSED" if ok else "E2E FAILED")

asyncio.run(main())
