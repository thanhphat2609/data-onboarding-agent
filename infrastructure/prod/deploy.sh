#!/usr/bin/env bash
# Deploys VM 1 to a commit. Run on the VM, from the repository checkout, by the Deploy workflow:
#   git fetch --prune origin && git show <sha>:infrastructure/prod/deploy.sh | bash -s -- <sha> [--no-cache]
# so the script of the target commit runs, not the one currently checked out.
#   --no-cache  rebuild every image layer (default: reuse the cache, but always pull newer base images)
set -euo pipefail

sha="${1:?commit sha}"
shift
no_cache=()
for arg in "$@"; do
  case "$arg" in
    --no-cache) no_cache=(--no-cache) ;;
    *) echo "Unknown option $arg" >&2; exit 2 ;;
  esac
done

compose=(docker compose -f infrastructure/prod/docker-compose.yml)

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "::error::Uncommitted changes in $(pwd); commit or discard them, then re-run the deploy:" >&2
  git status --short >&2
  exit 1
fi

echo "Deploying: $(git rev-parse --short HEAD) -> ${sha:0:7}"
git checkout --quiet --detach "$sha"

# PostgreSQL keeps running unless its settings change; only the app is rebuilt and recreated.
"${compose[@]}" build --pull "${no_cache[@]}"
"${compose[@]}" up -d --remove-orphans --wait --wait-timeout 300

docker image prune -f
docker builder prune -f --filter until=168h
"${compose[@]}" ps
echo "VM 1 at ${sha:0:7}"
