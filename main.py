"""
AI Agent Platform Entrypoint.
Boots the FastAPI application server using Uvicorn.
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    # psycopg's async driver requires a Selector event loop on Windows; set the
    # policy before uvicorn creates the loop so the Postgres checkpointer works.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

from src.utils.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.api.gateway:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "dev",
    )
