# Z-Apply Backend

Local, async FastAPI transport for `z-apply-core`. It persists run metadata and
sanitized operational events in PostgreSQL, then streams committed events over
SSE to the cockpit.

The browser live-view endpoint also issues a short opaque token for a built-in
WebSocket-to-VNC bridge. The frontend passes the returned `websocket_url`
directly to noVNC; x11vnc remains bound to localhost and no separate websockify
process is required.

## Run locally (the only command you need)

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync --group dev
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head          # once, after schema migrations
UV_CACHE_DIR=/tmp/uv-cache uv run dev
```

Run it from the `z-apply-backend` directory. The API binds to
`127.0.0.1:8000`; verify with `curl http://127.0.0.1:8000/api/v1/health`.
`uv run start` does the same without auto-reload, for production-style runs.

### Why reload watches three repos (read this once, then never think about it again)

`uv run dev` resolves through `[project.scripts]` in `pyproject.toml` to
`z_apply_backend.cli:dev`, which configures uvicorn for you:

- The app is passed as a factory (`z_apply_backend.app:create_app` is a
  *function that builds the app*, not the app itself). FastAPI's own
  `fastapi dev` CLI cannot call factories, so don't use it here.
- The reloader watches ALL THREE repos. `z-apply-core` and
  `playwright-python-mcp` are installed as editable packages, so their source
  lives outside this directory. Without that, edits to them would silently
  require a manual restart. With it, any `.py` change in the
  backend, core, or browser backend restarts the server and picks up the new
  code automatically. **Never manually restart after a code edit.**

### Operational notes

- Logs go to stdout of the launching shell (or your nohup/tmux session).
- Put the local asyncpg connection string in `Z_APPLY_DATABASE_URL`; no
  secrets are returned by diagnostics routes.
- If the backend process stops while applications are active, those database
  rows are marked `interrupted` on the next start and are **not** retried
  automatically. This prevents duplicate application actions after an
  ambiguous process crash.
- The frontend is a separate process in `../z-apply-frontend`.
