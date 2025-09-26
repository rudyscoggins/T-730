#!/usr/bin/env bash
set -e

if [[ ! -f /app/data/creds.json || "${OAUTH_FORCE}" == "1" ]]; then
  echo "??  First run: generate Google creds"
  python -m bot.youtube.auth
  exit 0
fi

python -m bot.main
