from __future__ import annotations

import uvicorn
from fastapi import FastAPI


def serve(app: FastAPI, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Serve an already-configured Local_TTS app on loopback by default."""
    uvicorn.run(app, host=host, port=port)
