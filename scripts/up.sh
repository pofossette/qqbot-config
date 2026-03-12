#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-default}"

mkdir -p data napcat/config napcat/qq

if [[ ! -f .env ]]; then
  if [[ "$MODE" == "--domestic" ]]; then
    cp .env.domestic.example .env
  else
    cp .env.example .env
  fi
  sed -i "s/^NAPCAT_UID=.*/NAPCAT_UID=$(id -u)/" .env
  sed -i "s/^NAPCAT_GID=.*/NAPCAT_GID=$(id -g)/" .env
fi

docker compose up -d

cat <<'EOF'

Services started.

Next:
1. Open AstrBot: http://<server-ip>:6185
2. Open NapCat:  http://<server-ip>:6099/webui
3. Login QQ in NapCat WebUI
4. In AstrBot create a OneBot v11 bot:
   host=0.0.0.0 port=6199
5. In NapCat add WebSockets Client:
   url=ws://astrbot:6199/ws

AstrBot default credentials:
username: astrbot
password: astrbot
EOF
