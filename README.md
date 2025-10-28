# T-730

Self-hosted Discord bot that exposes a `/addradio` slash command for adding YouTube links to a shared playlist via the YouTube Data API v3. Designed to run on a Raspberry Pi in Docker.

## Quick Start (Raspberry Pi)
1. Choose stack directory on RPIZelda (`192.168.86.41`):
   - Staging: `~/docker/T-730/T-730-Staging`
   - Production: `~/docker/T-730/T-730-Prod`
2. Copy env and configure:
   - `cp .env.example .env`
   - Set `DISCORD_TOKEN`, `CHANNEL_ID`, `PLAYLIST_ID`, `COMPOSE_PROJECT_NAME`, `HEALTH_PORT` (and optionally `OAUTH_PORT`, `HOST_UID`, `HOST_GID`).
3. Add Google OAuth client secrets:
   - Place `data/client_secrets.json` (or point `GOOGLE_CLIENT_SECRET_FILE` to it).
4. Build and run (Compose service is `radiobot`):
   - `docker compose up -d --build`
5. Complete first-run OAuth (via SSH tunnel):
   - From your laptop: `ssh -L 8080:localhost:8080 pi@192.168.86.41`
   - Open `http://localhost:${OAUTH_PORT:-8080}` and authorize.
   - Tokens persist at `data/creds.json`.
6. Verify health:
   - `curl http://localhost:${HEALTH_PORT}/healthz` → `{ "status": "ok", ... }`

## Local Development
- Create venv and install deps:
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r bot/requirements.txt`
- Run the bot (requires `.env`):
  - `python -m bot.main`
- Optional dev deps and tests:
  - `pip install -r requirements-dev.txt`
  - `pytest -q`

## OAuth Setup
- Required files in `data/`:
  - `client_secrets.json` (download from Google Cloud Console)
  - `creds.json` (generated on first run)
- Re-auth if needed:
  - Local: `python -m bot.youtube.auth`
  - Docker: `docker compose run --rm -e OAUTH_FORCE=1 radiobot`

## Bot Behavior
- Provides a `/addradio` slash command that accepts a YouTube URL (`youtu.be/...` or `youtube.com/watch?v=`).
- Extracts the video ID, appends to the playlist, and skips duplicates.
- Shares success summaries privately with the caller and posts a public announcement embed in the configured channel.
- Exposes `GET /healthz` on `HEALTH_PORT` for liveness/readiness.

## Troubleshooting
- Pi wheels SSL errors: force PyPI-only install locally if needed:
  - `PIP_CONFIG_FILE=$(mktemp) PIP_EXTRA_INDEX_URL= pip install --no-cache-dir --index-url https://pypi.org/simple -r bot/requirements.txt`
- OAuth issues: delete `data/creds.json` and re-run (or use `OAUTH_FORCE=1`). Ensure SSH tunnel matches `OAUTH_PORT`.
- Permissions: set `HOST_UID`/`HOST_GID` in `.env` so the container can write to `data/`.

## Configuration
Set via `.env`:
- `DISCORD_TOKEN`, `CHANNEL_ID`, `PLAYLIST_ID`
- `OAUTH_PORT` (OAuth callback), `HEALTH_PORT` (health endpoint)
- `COMPOSE_PROJECT_NAME`, `HOST_UID`, `HOST_GID`
- `GOOGLE_CLIENT_SECRET_FILE` (optional path override)

## Deploy to Production
1. Merge PRs into `main` on GitHub.
2. On RPIZelda:
   - `cd ~/docker/T-730/T-730-Prod`
   - `git pull origin main`
   - Stop the existing stack to ensure the old container is gone:
     - `docker compose down`
   - Rebuild and recreate the production bot with a fresh image:
     - `docker compose build --no-cache radiobot`
     - `docker compose up -d --force-recreate radiobot`
   - Confirm the new build is running (optional):
     - `docker compose ps`
     - `docker compose logs -f radiobot`
