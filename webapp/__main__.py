"""Launch the local web UI: python -m webapp  (then open http://127.0.0.1:8000)"""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("WPMIGRATE_HOST", "127.0.0.1")
    port = int(os.environ.get("WPMIGRATE_PORT", "8000"))
    print(f"wp-migrator UI running at http://{host}:{port}")
    uvicorn.run("webapp.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
