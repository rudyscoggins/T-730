#!/usr/bin/env bash
set -e

# Disable aiohttp C-extensions by default to avoid libz/glibc issues
# on some ARM builds. Can be overridden via env if desired.
export AIOHTTP_NO_EXTENSIONS="${AIOHTTP_NO_EXTENSIONS:-1}"
export YARL_NO_EXTENSIONS="${YARL_NO_EXTENSIONS:-1}"
export MULTIDICT_NO_EXTENSIONS="${MULTIDICT_NO_EXTENSIONS:-1}"
export FROZENLIST_NO_EXTENSIONS="${FROZENLIST_NO_EXTENSIONS:-1}"

if [[ ! -f /app/data/creds.json || "${OAUTH_FORCE}" == "1" ]]; then
  echo "??  First run: generate Google creds"
  python -m bot.youtube.auth
  exit 0
fi

python -m bot.main
