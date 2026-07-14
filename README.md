# Z-Apply Backend

Local, async FastAPI transport for `z-apply-core`. It persists run metadata and
sanitized operational events in PostgreSQL, then streams committed events over
SSE to the cockpit.

The browser live-view endpoint also issues a short opaque token for a built-in
WebSocket-to-VNC bridge. The frontend passes the returned `websocket_url`
directly to noVNC; x11vnc remains bound to localhost and no separate websockify
process is required.

## Run locally

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync --group dev
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
UV_CACHE_DIR=/tmp/uv-cache uv run uvicorn z_apply_backend.app:create_app --factory --reload
```

The API binds to `127.0.0.1:8000` and uses the PostgreSQL server installed on
this machine. Put the local asyncpg connection string in
`Z_APPLY_DATABASE_URL`; no secrets are returned by diagnostics routes. Run the
Alembic command once after provisioning the local database and after pulling a
schema migration.

If the backend process stops while applications are active, those database rows
are marked `interrupted` on the next start and are **not** retried automatically.
This prevents duplicate application actions after an ambiguous process crash.

The frontend is a separate process in `../z-apply-frontend`.
