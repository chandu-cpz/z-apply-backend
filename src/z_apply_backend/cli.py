from __future__ import annotations

import os
import sys
from pathlib import Path


def _run(*, reload: bool) -> None:
    import uvicorn

    # Resolve dirs relative to this backend package so --reload watches
    # everything that affects the server, even when invoked from any cwd.
    backend_root = Path(__file__).resolve().parents[2]  # z-apply-backend/
    core_src = (backend_root.parent / "z-apply-core" / "src").resolve()
    mcp_src = (backend_root.parent / "playwright-python-mcp" / "src").resolve()

    reload_dirs = [str(backend_root)]
    for p in (core_src, mcp_src):
        if p.is_dir():
            reload_dirs.append(str(p))

    kwargs: dict = {
        "host": os.environ.get("Z_APPLY_HOST", "127.0.0.1"),
        "port": int(os.environ.get("Z_APPLY_PORT", "8000")),
        "factory": True,
        "reload": reload,
    }
    if reload:
        kwargs["reload_dirs"] = reload_dirs

    # uvicorn.run blocks; reload mode spawns a watcher subprocess.
    uvicorn.run("z_apply_backend.app:create_app", **kwargs)


def dev() -> None:
    """Run backend with auto-reload (watches backend + core + mcp). Like `npm run dev`."""
    _run(reload=True)


def start() -> None:
    """Run backend without reload (production). Like `npm start`."""
    _run(reload=False)


if __name__ == "__main__":
    # Allow `python -m z_apply_backend.cli dev|start` as well.
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if cmd == "start":
        start()
    else:
        dev()
