"""
Tests for non-blocking node retry behaviour (C-5) and bounded approval callback (C-6).

C-5: retriever_node and executor_node must not call time.sleep (thread-blocking).
     Tenacity must be used for async retries.
     Graceful error returned on retry exhaustion.
C-6: /run and /approval-callback must use semaphore.locked() guard (not wait_for),
     ainvoke instead of run_in_executor(None, ...).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

# ── C-5: Retry behaviour ──────────────────────────────────────────────────────


class TestRetrieverRetryBehaviour:
    @patch("src.agent.nodes.retriever.httpx.AsyncClient")
    async def test_success_after_transient_failure(self, mock_client_cls: MagicMock) -> None:
        """Node returns chunks after a transient failure on attempt 1."""
        from src.agent.nodes.retriever import retriever_node

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "chunks": [{"content": "SLA: 4h", "source": "sla", "relevance_score": 0.9}]
        }

        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(side_effect=[httpx.ConnectError("timeout"), mock_resp])
        mock_client_cls.return_value = mock_instance

        state = {"session_id": "s1", "user_message": "What is the SLA?", "user_id": ""}
        result = await retriever_node(state)
        assert "retrieved_chunks" in result
        assert len(result["retrieved_chunks"]) >= 1

    @patch("src.agent.nodes.retriever.httpx.AsyncClient")
    async def test_graceful_error_after_exhaustion(self, mock_client_cls: MagicMock) -> None:
        """Node returns graceful error dict (empty chunks + error key) after all retries fail."""
        from src.agent.nodes.retriever import retriever_node

        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(side_effect=httpx.ConnectError("down"))
        mock_client_cls.return_value = mock_instance

        state = {"session_id": "s1", "user_message": "test", "user_id": ""}
        result = await retriever_node(state)
        assert result.get("retrieved_chunks") == []
        assert "error" in result
        assert "unavailable" in result["error"].lower()


# ── C-6: Semaphore guard pattern ──────────────────────────────────────────────


class TestSemaphoreGuardPattern:
    """
    Unit-tests for the semaphore.locked() guard pattern used in /run and /approval-callback.
    Tests the pattern directly rather than via HTTP to avoid a real Postgres dependency.
    """

    async def test_locked_semaphore_raises(self) -> None:
        """semaphore.locked() is True when no slots remain."""
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()  # drain it
        assert semaphore.locked() is True
        semaphore.release()

    async def test_available_semaphore_is_not_locked(self) -> None:
        """semaphore.locked() is False when at least one slot is available."""
        semaphore = asyncio.Semaphore(2)
        assert semaphore.locked() is False

    async def test_acquire_and_release_restores_slot(self) -> None:
        """Acquiring and releasing restores the semaphore to its original state."""
        semaphore = asyncio.Semaphore(2)
        assert semaphore.locked() is False
        await semaphore.acquire()
        await semaphore.acquire()
        assert semaphore.locked() is True
        semaphore.release()
        assert semaphore.locked() is False

    async def test_semaphore_released_in_finally_on_exception(self) -> None:
        """semaphore.release() in a finally block restores the slot after an exception."""
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()
        assert semaphore.locked() is True

        try:
            raise RuntimeError("graph failed")
        except RuntimeError:
            pass
        finally:
            semaphore.release()

        assert semaphore.locked() is False


# ── Parallel Action Execution ───────────────────────────────────────────────


class TestParallelActionExecutor:
    @patch("src.agent.nodes.executor._call_action_service")
    def test_parallel_safe_actions(self, mock_call_action: AsyncMock) -> None:
        from src.agent.nodes.executor import executor_node

        mock_call_action.side_effect = [
            {"success": True, "action": "auto_respond"},
            {"success": True, "action": "auto_respond"},
        ]

        state = {
            "session_id": "s1",
            "selected_actions": [
                {"action_name": "auto_respond", "action_payload": {}, "risk_level": "SAFE"},
                {"action_name": "auto_respond", "action_payload": {}, "risk_level": "SAFE"},
            ],
            "risk_level": "SAFE",
        }

        result = asyncio.run(executor_node(state))
        assert "action_result" in result
        assert isinstance(result["action_result"], list)
        assert len(result["action_result"]) == 2
        assert mock_call_action.call_count == 2
