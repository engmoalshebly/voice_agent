#!/usr/bin/env bash
set -euo pipefail

docker inspect darai-voice-web-before-ctm-test >/dev/null
docker stop darai-voice-web
docker rename darai-voice-web darai-voice-web-ctm-test-stopped
docker rename darai-voice-web-before-ctm-test darai-voice-web
docker start darai-voice-web
docker stop darai-voice-agent-ctm-test
