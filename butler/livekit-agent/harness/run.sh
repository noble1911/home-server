#!/bin/bash
# Local end-to-end voice test: the real app in headless Chrome, LiveKit and the
# real agent in Docker (as on the Mini), Whisper standing in for Groq. Each
# scenario presses the mic three times (one cold, two warm) and reports what
# Butler heard. See README.md.
#   ./run.sh                 # every scenario at 0 and 50 ms latency
#   LATENCIES=300 ./run.sh   # a slow connection
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$(dirname "$HERE")"
REPO="$(cd "$AGENT_DIR/../.." && pwd)"
WORK="$HERE/.work"
LATENCIES="${LATENCIES:-0 50}"
NET=butler-voice-harness
LK_IP=172.30.9.10  # LiveKit advertises this; Docker Desktop/OrbStack route the Mac to container IPs

VITE_PID=
cleanup() {
  docker rm -f harness-livekit harness-butler harness-agent >/dev/null 2>&1
  [ -n "$VITE_PID" ] && kill "$VITE_PID" 2>/dev/null
  return 0
}
trap cleanup EXIT

echo "==> Test speech"
mkdir -p "$WORK"
say_wav() {  # name, text
  [ -f "$WORK/$1.wav" ] && return
  say -v Samantha -r 170 -o "$WORK/$1.aiff" "$2"
  ffmpeg -loglevel error -y -i "$WORK/$1.aiff" -ar 48000 -ac 1 "$WORK/$1.wav"
}
say_wav short "Turn off the kitchen lights."
say_wav speech "One, two, three, four, five, six, seven, eight."
say_wav p1 "One, two, three, four."
say_wav p2 "Five, six, seven, eight."
[ -f "$WORK/pause.wav" ] || ffmpeg -loglevel error -y -i "$WORK/p1.wav" -f lavfi -t 1.6 -i anullsrc=r=48000:cl=mono \
  -i "$WORK/p2.wav" -filter_complex "[0:a][1:a][2:a]concat=n=3:v=0:a=1" -ar 48000 -ac 1 "$WORK/pause.wav"

echo "==> LiveKit, fake Butler API and agent (Docker)"
cleanup
docker network inspect $NET >/dev/null 2>&1 || docker network create --subnet 172.30.9.0/24 $NET >/dev/null
docker build -q -t butler-voice-harness -f "$HERE/Dockerfile" "$AGENT_DIR" >/dev/null || exit 1
docker run -d --name harness-livekit --network $NET --ip $LK_IP -p 17880:7880 \
  livekit/livekit-server:v1.9.11 --dev --bind 0.0.0.0 --node-ip $LK_IP >/dev/null
docker run -d --name harness-butler --network $NET -p 18000:18000 \
  -v "$REPO/butler:/butler:ro" -v "$HERE:/harness:ro" -v "$WORK:/work:ro" \
  butler-voice-harness python -u /harness/fake_butler.py >/dev/null
docker run -d --name harness-agent --network $NET \
  -v "$AGENT_DIR:/agent:ro" -v "$HERE:/harness:ro" -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -e LIVEKIT_URL=ws://$LK_IP:7880 -e BUTLER_API_URL=http://harness-butler:18000 -e KOKORO_URL=http://harness-butler:18000 \
  butler-voice-harness python -u /harness/run_agent.py >/dev/null
for _ in $(seq 1 120); do docker logs harness-agent 2>&1 | grep -q "registered worker" && break; sleep 1; done
docker logs harness-agent 2>&1 | grep -q "registered worker" || { echo "agent didn't start:"; docker logs harness-agent 2>&1 | tail -20; exit 1; }

echo "==> App (vite) and browser driver"
(cd "$HERE" && npm install --silent --no-audit --no-fund) || exit 1
# exec, so $! is vite itself (cleanup kills it by PID); run from app/ for its config
(cd "$REPO/app" && VITE_LIVEKIT_URL=ws://localhost:17880 VITE_API_URL=http://localhost:18000/api \
  exec ./node_modules/.bin/vite --port 15173 --strictPort >"$WORK/vite.log" 2>&1) &
VITE_PID=$!
for _ in $(seq 1 60); do curl -s -o /dev/null localhost:15173 && break; sleep 1; done

failed=0
for lat in $LATENCIES; do
  for scenario in "short|turn,off,kitchen,lights" "speech|1,2,3,4,5,6,7,8" "pause|1,2,3,4,5,6,7,8"; do
    IFS='|' read -r name expect <<< "$scenario"
    echo "== $name.wav, ${lat}ms latency"
    (cd "$HERE" && LATENCY_MS=$lat SPEECH=$name.wav EXPECT=$expect node voice_test.mjs) || failed=$((failed + 1))
  done
done
echo
[ $failed -eq 0 ] && echo "PASSED: every word heard, one request per press" || echo "FAILED: $failed scenario(s); agent log: docker logs harness-agent"
exit $((failed > 0))
