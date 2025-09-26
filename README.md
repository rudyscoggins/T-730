# 730RadioBot

Discord bot that adds YouTube links (tagged with a keyword) to a playlist using the YouTube Data API.

## Local Development
- Create venv and install deps:
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r bot/requirements.txt`
  - (optional for tests) `pip install -r requirements-dev.txt`
- Run the bot (requires `.env`):
  - `python -m bot.main`

First run needs YouTube OAuth credentials in `data/`:
- Place your Google OAuth client JSON at `data/client_secrets.json`.
- Generate user creds: `python -m bot.youtube.auth` (saves `data/creds.json`).

## Raspberry Pi: PyPI‑only installs (piwheels SSL workaround)
On some Pi setups, pip may hit SSL errors from `piwheels.org` (e.g., certificate expired) when installing Google client libs. To force a PyPI‑only install just for this session, run:

- `python -m venv .venv && source .venv/bin/activate`
- `PIP_CONFIG_FILE=$(mktemp) PIP_EXTRA_INDEX_URL= pip install --no-cache-dir --index-url https://pypi.org/simple -r bot/requirements.txt`

Optional extras:
- Lint: `pip install ruff && ruff check bot`
- Quick import check: `python -c "import bot.main; print('Import OK')"`

## Docker
- Build and run: `docker compose up --build radiobot`
- First run triggers OAuth helper inside the container to create `data/creds.json`.

## Testing
- Install dev deps: `pip install -r requirements-dev.txt`
- Run tests: `pytest -q`

Notes:
- Tests mock Discord and YouTube clients; no network calls are made.
- Importing `bot.main` will not start the client; it runs only under `python -m bot.main`.

## Health Check
- The bot starts a lightweight HTTP endpoint for liveness/readiness:
  - URL: `http://localhost:${HEALTH_PORT:-8081}/healthz`
  - Response: `{ "status": "ok", "ready": true|false, "uptime_s": <int> }`
- On startup, logs a single `READY` line with playlist, channel, and health URL.
- Configure host/port via env: `HEALTH_HOST`, `HEALTH_PORT`.

## Token Rotation (Google OAuth)
- If YouTube credentials expire or are revoked, the bot will reply with a clear
  re-auth message in Discord and log an error.
- Re-auth options:
  - Local: `python -m bot.youtube.auth`
  - Docker: `docker compose run --rm -e OAUTH_FORCE=1 radiobot`
- This regenerates `data/creds.json`. You can also delete `data/creds.json` and run the container to trigger auth.

## Configuration
Copy `.env.example` to `.env` and fill in:
- `DISCORD_TOKEN`, `CHANNEL_ID`, `PLAYLIST_ID`
- Optional: `OAUTH_PORT` for local-server OAuth mode
