"""Supervise best-effort tasks that outlive a request."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class BackgroundTaskSupervisor:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule(
        self, coroutine: Coroutine[Any, Any, None], *, task_name: str, session_id: str
    ) -> None:
        task = asyncio.create_task(coroutine, name=task_name)
        self._tasks.add(task)

        def completed(done: asyncio.Task[None]) -> None:
            self._tasks.discard(done)
            try:
                done.result()
            except asyncio.CancelledError:
                log.info("background_task.cancelled", task=task_name, session_id=session_id)
            except Exception as exc:
                log.error(
                    "background_task.failed",
                    task=task_name,
                    session_id=session_id,
                    error=exc.__class__.__name__,
                )

        task.add_done_callback(completed)

    async def drain(self, timeout_seconds: float = 2.0) -> None:
        if not self._tasks:
            return
        done, pending = await asyncio.wait(self._tasks, timeout=timeout_seconds)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


background_tasks = BackgroundTaskSupervisor()
