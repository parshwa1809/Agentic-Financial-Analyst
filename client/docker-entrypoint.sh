#!/bin/sh
set -e

# Determine API base URL for runtime config. Preference order:
# 1) RUNTIME_API_BASE env var passed to container
# 2) VITE_API_BASE baked into image at build-time (if present)
# 3) fallback to localhost

API_BASE="${RUNTIME_API_BASE:-${VITE_API_BASE:-http://localhost:8000/api}}"

# Write runtime config file used by the SPA to read API base at runtime
cat > /usr/share/nginx/html/runtime-config.js <<EOF
window.__API_BASE__ = "${API_BASE}";
EOF

# If an extra command is provided, run it (exec). Otherwise exec the default CMD (nginx).
exec "$@"
