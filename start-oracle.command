#!/bin/bash
# Project Oracle — one-click start.
# Double-click this file (or let VS Code run it when the folder opens) to:
#   1. start Docker Desktop and Ollama if they aren't running
#   2. rebuild and start every container with the latest code
#   3. backfill missing price history (the `backfill` service runs automatically)
#   4. open the dashboard once the API answers
set -u
cd "$(dirname "$0")"

say() { printf "\n\033[1;35m▶ %s\033[0m\n" "$1"; }

say "Starting Docker Desktop and Ollama…"
docker info >/dev/null 2>&1 || open -a Docker || { echo "❌ Docker Desktop not found — install it from docker.com"; exit 1; }
pgrep -xq ollama || pgrep -fq "Ollama.app" || open -a Ollama 2>/dev/null || echo "⚠️  Ollama not found — AI chat/council will be unavailable (ollama.com)"

# Models the agents need (downloaded once, then skipped)
OLLAMA_MODEL_NAME=$(grep -E '^OLLAMA_MODEL_NAME=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'"' ')
if command -v ollama >/dev/null 2>&1; then
  for i in $(seq 1 15); do ollama list >/dev/null 2>&1 && break; sleep 2; done
  for m in nomic-embed-text "${OLLAMA_MODEL_NAME:-phi3:mini}"; do
    ollama list 2>/dev/null | grep -q "^${m%%:*}" || { say "Downloading AI model $m (one time)…"; ollama pull "$m"; }
  done
fi

printf "Waiting for Docker"
for i in $(seq 1 90); do docker info >/dev/null 2>&1 && break; printf "."; sleep 2; done
docker info >/dev/null 2>&1 || { echo; echo "❌ Docker didn't start within 3 minutes."; exit 1; }
echo " ready."

say "Building and starting containers (latest code)…"
docker compose up -d --build --force-recreate --remove-orphans || { echo "❌ docker compose failed — see the output above."; exit 1; }

printf "Waiting for the API"
for i in $(seq 1 60); do curl -fs http://localhost/api/health >/dev/null 2>&1 && break; printf "."; sleep 2; done
echo
if curl -fs http://localhost/api/health >/dev/null 2>&1; then
  say "Project Oracle is up → http://localhost"
  open http://localhost
else
  echo "⚠️  The API isn't answering yet. Check: docker compose logs --tail 40 api"
fi

say "Agent status"
STATUS_JSON=$(curl -fs http://localhost/api/system/status 2>/dev/null) && python3 - "$STATUS_JSON" <<'PY' || true
import json, sys
d = json.loads(sys.argv[1])
m = d["market"]
print("Market:", "open" if m["open"] else "closed", "·", m["now_et"])
for a in d["agents"]:
    print("  %7s  %s: %s" % (a["status"], a["label"], a["detail"]))
PY
echo
echo "Price backfill is running in the background:  docker compose logs -f backfill"
