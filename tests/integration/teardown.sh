#!/usr/bin/env bash
# Destroy the disposable Moodle test site: containers, both named volumes
# (database + moodledata), the extracted code dir and seed-ids.json.
#
#   ./teardown.sh          # keeps .env (credentials) and dl/ (tarball cache)
#   ./teardown.sh --all    # also deletes .env, dl/ and install.log
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# Compose needs the variable for interpolation even when only tearing down.
export MOODLE_DB_PASSWORD="${MOODLE_DB_PASSWORD:-unused-for-teardown}"
if [ -f .env ]; then set -a; . ./.env; set +a; fi

docker compose -p moodle-it -f "$HERE/docker-compose.yml" down -v --remove-orphans

# config.php is owned by the container's www-data, but it lives in a directory
# we own, so a plain rm can unlink it.
rm -rf "$HERE/moodle" "$HERE/moodle.tmp" "$HERE/seed-ids.json" "$HERE/seed-ids.json.tmp"

if [ "${1:-}" = "--all" ]; then
    rm -rf "$HERE/.env" "$HERE/dl" "$HERE/install.log"
    echo "[teardown] removed stack, volumes, code, .env, dl/ and install.log"
else
    echo "[teardown] removed stack, volumes, code and seed-ids.json (kept .env and dl/; use --all to drop them)"
fi
