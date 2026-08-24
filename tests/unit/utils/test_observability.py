"""
Unit tests for Langfuse LLM Observability callback fallback.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.utils.observability import get_langfuse_callback_handler


class TestObservability:
    def test_fallback_when_keys_missing(self) -> None:
        with patch("src.utils.observability.settings") as mock_settings:
            mock_settings.langfuse_public_key = ""
            mock_settings.langfuse_secret_key = ""

            handlers = get_langfuse_callback_handler()
            assert handlers == []

    def test_instantiates_handler_when_keys_present(self) -> None:
        mock_client = MagicMock()

        with (
            patch("src.utils.observability.settings") as mock_settings,
            patch("langfuse.langchain.CallbackHandler", return_value=mock_client),
        ):
            mock_settings.langfuse_public_key = "pk-test"
            mock_settings.langfuse_secret_key = "sk-test"
            mock_settings.langfuse_host = "https://cloud.langfuse.com"

            handlers = get_langfuse_callback_handler()
            assert len(handlers) == 1
            assert handlers[0] == mock_client
