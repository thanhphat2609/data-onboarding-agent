#!/usr/bin/env bash
# GitHub Codespaces: let Docker compose networks through the legacy firewall.
# Docker 29 writes its rules to nf_tables, but the codespace also has iptables-legacy rules with
# "-P FORWARD DROP" that only allow docker0, so the app can't reach postgres or the internet.
# Runs on every codespace start (.devcontainer/devcontainer.json); safe to run again by hand.
# Details: infrastructure/README.md#codespaces-containers-cant-reach-each-other-or-the-internet
set -euo pipefail

command -v iptables-legacy >/dev/null 2>&1 || exit 0

# Docker creates its rules when the daemon starts, so wait for it first (up to 60 s).
for _ in $(seq 1 30); do
  docker info >/dev/null 2>&1 && break
  sleep 2
done

if sudo iptables-legacy -S FORWARD 2>/dev/null | grep -qx -- '-P FORWARD DROP'; then
  sudo iptables-legacy -P FORWARD ACCEPT
  echo "codespace-network: iptables-legacy FORWARD policy set to ACCEPT (compose networks were blocked)"
else
  echo "codespace-network: nothing to do"
fi
