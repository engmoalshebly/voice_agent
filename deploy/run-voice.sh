#!/usr/bin/env bash
# (Re)start the voice web + agent containers on the DarAI host.
# Usage: deploy/run-voice.sh [web|agent|all]   (LiveKit is managed separately)
#
# VOICE_MODE=darai (default): a call is a DarAI webchat conversation, spoken.
#   The agent talks to the realtime gateway on the app network; the page gets
#   its tokens from the public gateway for VOICE_CHANNEL_ID (a webchat widget
#   id, whose allowed origins must include this page's origin).
# VOICE_MODE=cascade|live|pipeline: the earlier demo modes (developer channel).
#
# Secrets live in /opt/darai/secrets/voice, never in Git:
#   livekit.env          LIVEKIT_API_KEY, LIVEKIT_API_SECRET
#   agent.env            speech provider keys (and the demo modes' DarAI key)
#   gateway-worker.env   VOICE_WORKER_KEY (the same file the gateway reads)
set -euo pipefail
D=/opt/darai/secrets/voice
IMAGE=${IMAGE:-darai-voice-web:20261117}
NET=darai_edge_net
APP_NET=darai_app_net
MODE=${VOICE_MODE:-darai}
GATEWAY_PUBLIC_URL=${VOICE_GATEWAY_PUBLIC_URL:-https://devdarai.prideidea.com}
GATEWAY_INTERNAL_URL=${DARAI_GATEWAY_URL:-http://darai_realtime_gateway:5080}
CHANNEL_ID=${VOICE_CHANNEL_ID:-}
what=${1:-all}

if [[ $MODE == darai && -z $CHANNEL_ID && $what != agent ]]; then
  echo "VOICE_CHANNEL_ID is required in darai mode (the webchat widget id calls belong to)" >&2
  exit 2
fi

if [[ $what == web || $what == all ]]; then
  web_env=()
  if [[ $MODE == darai ]]; then
    web_env=(-e "VOICE_GATEWAY_PUBLIC_URL=$GATEWAY_PUBLIC_URL" -e "VOICE_CHANNEL_ID=$CHANNEL_ID")
  fi
  docker rm -f darai-voice-web >/dev/null 2>&1 || true
  docker run -d --name darai-voice-web --restart unless-stopped --network "$NET" \
    -e WEB_ORIGIN=https://voice.prideidea.com -e WEB_HOST=0.0.0.0 -e TRUST_PROXY=true \
    -e LIVEKIT_URL=wss://rtc.prideidea.com --env-file "$D/livekit.env" "${web_env[@]}" \
    --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --memory 256m \
    "$IMAGE"
fi

if [[ $what == agent || $what == all ]]; then
  agent_env=()
  if [[ $MODE == darai ]]; then
    agent_env=(-e "DARAI_GATEWAY_URL=$GATEWAY_INTERNAL_URL" --env-file "$D/gateway-worker.env")
  fi
  docker rm -f darai-voice-agent >/dev/null 2>&1 || true
  # cpu-shares: real-time audio must win CPU contention on this shared 4-core host.
  docker run -d --name darai-voice-agent --restart unless-stopped --network "$NET" \
    -e LIVEKIT_URL=ws://darai-livekit:7880 -e "VOICE_MODE=$MODE" -e VOICE_PROVIDER=openai \
    -e AGENT_IDLE_PROCESSES=1 -e OMP_NUM_THREADS=1 \
    --env-file "$D/livekit.env" --env-file "$D/agent.env" "${agent_env[@]}" \
    --cpu-shares 4096 --cap-drop ALL --security-opt no-new-privileges --memory 2g \
    "$IMAGE" voice-agent start
  if [[ $MODE == darai ]]; then
    # The gateway is on the app network; LiveKit is on the edge network.
    docker network connect "$APP_NET" darai-voice-agent
  fi
fi
