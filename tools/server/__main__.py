"""Entry point: `python -m tools.server` boots the FastAPI app on :8765."""
from __future__ import annotations
import argparse
import uvicorn


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--reload", action="store_true", help="enable auto-reload (dev)")
    args = p.parse_args()
    uvicorn.run(
        "tools.server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
