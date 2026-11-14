#!/usr/bin/env bash
# (Re)start the voice web + agent containers on the DarAI host.
# Usage: deploy/run-voice.sh [web|agent|all]   (LiveKit is managed separately)
# Secrets live in /opt/darai/secrets/voice (livekit.env, agent.env); never in Git.
set -euo pipefail
D=/opt/darai/secrets/voice
IMAGE=${IMAGE:-darai-voice-web:20261108}
NET=darai_edge_net
what=${1:-all}

if [[ $what == web || $what == all ]]; then
  docker rm -f darai-voice-web >/dev/null 2>&1 || true
  docker run -d --name darai-voice-web --restart unless-stopped --network "$NET" \
    -e WEB_ORIGIN=https://voice.prideidea.com -e WEB_HOST=0.0.0.0 -e TRUST_PROXY=true \
    -e LIVEKIT_URL=wss://rtc.prideidea.com --env-file "$D/livekit.env" \
    --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --memory 256m \
    "$IMAGE"
fi

if [[ $what == agent || $what == all ]]; then
  docker rm -f darai-voice-agent >/dev/null 2>&1 || true
  # cpu-shares: real-time audio must win CPU contention on this shared 4-core host.
  docker run -d --name darai-voice-agent --restart unless-stopped --network "$NET" \
    -e LIVEKIT_URL=ws://darai-livekit:7880 -e VOICE_MODE=cascade -e VOICE_PROVIDER=openai \
    -e AGENT_IDLE_PROCESSES=1 -e OMP_NUM_THREADS=1 \
    --env-file "$D/livekit.env" --env-file "$D/agent.env" \
    --cpu-shares 4096 --cap-drop ALL --security-opt no-new-privileges --memory 2g \
    "$IMAGE" voice-agent start
fi
