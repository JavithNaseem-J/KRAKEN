from __future__ import annotations

import asyncio
import os
import sys

if sys.platform == "win32":
    # psycopg's async driver requires a Selector event loop on Windows; set the
    # policy before uvicorn creates the loop so the Postgres checkpointer works.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    config = uvicorn.Config(
        "src.api.gateway:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("UVICORN_RELOAD", "false").lower() == "true",
    )
    server = uvicorn.Server(config)
    if sys.platform == "win32" and not config.should_reload:
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(server.serve())
    else:
        server.run()
