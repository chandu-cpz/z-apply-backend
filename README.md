# Z-Apply Backend

Local, async FastAPI transport for `z-apply-core`. It persists run metadata and
sanitized operational events in PostgreSQL, then streams committed events over
SSE to the cockpit.

## Run locally

```bash
docker compose up -d
UV_CACHE_DIR=/tmp/uv-cache uv sync --group dev
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
UV_CACHE_DIR=/tmp/uv-cache uv run uvicorn z_apply_backend.app:create_app --factory --reload
```

The API binds to `127.0.0.1:8000`. Set `Z_APPLY_DATABASE_URL` to change the
local asyncpg connection string; no secrets are returned by diagnostics routes.

The frontend is a separate process in `../z-apply-frontend`.
