#!/usr/bin/env bash
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
    echo "Tailscale is not installed."
    echo "Install: https://tailscale.com/download/mac"
    exit 1
fi

STATUS_JSON="$(tailscale status --json 2>/dev/null || true)"
if [ -z "$STATUS_JSON" ]; then
    echo "Tailscale is installed but not running. Run: tailscale up"
    exit 1
fi

IPV4="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
DNS_NAME="$(echo "$STATUS_JSON" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print((data.get("Self", {}).get("DNSName") or "").rstrip("."))
except Exception:
    pass
' || true)"

PORT="${WEBUI_PORT:-8080}"

echo "Tailscale is up."
echo ""
if [ -n "$IPV4" ]; then
    echo "  IPv4:        http://$IPV4:$PORT"
fi
if [ -n "$DNS_NAME" ]; then
    echo "  MagicDNS:    http://$DNS_NAME:$PORT"
fi
echo ""
echo "To expose Open WebUI on your tailnet:"
echo "  1) Set DEPLOY_MODE=tailscale in .env (or export it)"
echo "  2) make down && make up"
echo "  3) Share the URL above with users you've invited to your tailnet"
echo ""
echo "New users will see a signup screen, then wait for you to approve them"
echo "in Open WebUI > Admin Panel > Users."
