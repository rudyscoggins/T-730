# T-730 — Agent Guide

This document gives Codex CLI contributors a focused overview of how the T-730 repo is organized and deployed, plus practical tips for extending the bot.

## Project Overview
- Language: Python 3.12
- Libraries: `discord.py`, `aiohttp`, `google-auth-oauthlib`, `google-api-python-client`
- Purpose: A self-hosted Discord bot that listens for messages containing the keyword "730Radio" plus a YouTube link and adds that video to a shared playlist via the YouTube Data API v3. Runs on a Raspberry Pi inside Docker.

## Deployment Architecture
Two isolated Docker Compose stacks live on RPIZelda (`192.168.86.41`):

| Environment | Path                                  | Compose Project | Container        | Discord Bot         | Notes            |
| ----------- | ------------------------------------- | --------------- | ---------------- | ------------------- | ---------------- |
| Production  | `/home/pi/docker/T-730/T-730-Prod`    | `t730_prod`     | `T-730`          | Main Discord server | Uses playlist A  |
| Staging     | `/home/pi/docker/T-730/T-730-Staging` | `t730_staging`  | `T-730-Staging`  | Test Discord server | Uses playlist B  |

- Stacks share identical source layout; only `.env` values differ.
- Manual deploy via `git pull` then `docker compose up -d --build`.
- Watchtower is disabled; rebuild manually.

## Directory Layout
```
T-730-*/
├─ bot/
│  ├─ main.py              # Discord message loop
│  └─ youtube/
│     ├─ auth.py           # OAuth + credential handling
│     └─ api.py            # Playlist insert logic
├─ docker/
│  ├─ Dockerfile
│  └─ entrypoint.sh
├─ data/                   # Persistent creds.json
├─ docker-compose.yml
├─ docker-compose.override.yml  # local-only
├─ .env / .env.example
├─ AGENTS.md
└─ README.md
```

## Environment Variables
| Variable                    | Description                                     |
| --------------------------- | ----------------------------------------------- |
| `DISCORD_TOKEN`             | Discord bot token                               |
| `CHANNEL_ID`                | Channel to monitor                              |
| `PLAYLIST_ID`               | Target YouTube playlist                         |
| `OAUTH_PORT`                | Local redirect port for Google OAuth            |
| `HEALTH_PORT`               | Port for internal `/healthz` endpoint           |
| `COMPOSE_PROJECT_NAME`      | Unique per stack (`t730_prod`/`t730_staging`)   |
| `HOST_UID`, `HOST_GID`      | Map host user for file writes                   |
| `GOOGLE_CLIENT_SECRET_FILE` | Path to OAuth client secrets JSON (mounted)     |

## Build, Run, and Test
- Local (Python):
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r bot/requirements.txt`
  - `python -m bot.main` (requires `.env`)
- Docker (Compose service is `radiobot`):
  - `docker compose up -d --build`
  - First run triggers OAuth helper to create `data/creds.json`.
- CI builds the image with `docker/Dockerfile` (multi-arch).

## Coding Style
- 4-space indentation, trailing commas where reasonable, 88–100 col width.
- Names: modules/functions `snake_case`, classes `CapWords`, constants `UPPER_SNAKE`.
- Prefer type hints and docstrings for public functions.
- Formatting: Black and isort; lint with Ruff or Flake8 (not enforced by CI yet).

## Testing
- No formal suite yet. If adding tests, use `pytest` under `tests/`.
- Name tests `test_*.py`; keep tests fast and hermetic (mock Discord/Google APIs).
- Example: `pytest -q` (after installing dev deps).

## Dev → Prod Workflow
1. Develop in `~/docker/T-730/T-730-Staging`:
   - `git checkout -b feat/my-feature`
   - `docker compose up -d --build`
2. Push & PR:
   - `git push -u origin feat/my-feature`
   - Open a PR against `main`.
3. Merge to `main` in GitHub.
4. Deploy to production:
   - `cd ~/docker/T-730/T-730-Prod && git pull origin main`
   - `docker compose up -d --build`

## Bot Behavior
- Detects keyword "730Radio" (case-insensitive) and YouTube links (`youtu.be/...` or `youtube.com/watch?v=...`).
- Extracts video ID; appends to playlist; skips duplicates.
- Reacts with ✅ on success, ❌ on failure.
- Exposes optional `/healthz` for uptime checks.

## Auth Flow
- Uses `google-auth-oauthlib` `run_local_server()` for OAuth.
- First run via SSH tunnel:
  - `ssh -L 8080:localhost:8080 pi@192.168.86.41`
- Tokens cached at `data/creds.json`.

## For Codex Developers
- Extend Discord features by adding modules under `bot/`:
  - Commands and listeners live near `bot/main.py` following `discord.py` patterns.
  - YouTube helpers in `bot/youtube/` (`auth.py` for tokens, `api.py` for playlist ops).
  - Keep I/O async with `aiohttp` where applicable.
- When changing behavior, update env var usage in `README.md` and ensure the OAuth cache in `data/` still works across rebuilds.
- Do not commit secrets. Use `.env` and mount `data/` for OAuth files (`client_secrets.json`, generated creds).
