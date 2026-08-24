"""
Unit tests for Langfuse LLM Observability callback fallback.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import src.utils.observability as obs_module
from src.utils.observability import (
    flush_langfuse,
    get_langfuse_callback_handler,
    get_langfuse_client,
)


@pytest.fixture(autouse=True)
def reset_langfuse_client_singleton():
    """Reset the global _langfuse_client singleton before and after each test."""
    obs_module._langfuse_client = None
    yield
    obs_module._langfuse_client = None


class TestObservability:
    def test_fallback_when_keys_missing(self) -> None:
        with patch("src.utils.observability.settings") as mock_settings:
            mock_settings.langfuse_public_key = ""
            mock_settings.langfuse_secret_key = ""

            handlers = get_langfuse_callback_handler()
            assert handlers == []

    def test_fallback_when_placeholder_keys_present(self) -> None:
        with patch("src.utils.observability.settings") as mock_settings:
            mock_settings.langfuse_public_key = "your-public-key-here"
            mock_settings.langfuse_secret_key = "your-secret-key-here"

            client = get_langfuse_client()
            assert client is None

            handlers = get_langfuse_callback_handler()
            assert handlers == []

    def test_instantiates_handler_when_keys_present(self) -> None:
        mock_handler = MagicMock()
        mock_client = MagicMock()

        with (
            patch("src.utils.observability.settings") as mock_settings,
            patch("src.utils.observability.get_langfuse_client", return_value=mock_client),
            patch("langfuse.langchain.CallbackHandler", return_value=mock_handler),
        ):
            mock_settings.langfuse_public_key = "pk-test"
            mock_settings.langfuse_secret_key = "sk-test"
            mock_settings.langfuse_host = "https://cloud.langfuse.com"

            handlers = get_langfuse_callback_handler()
            assert len(handlers) == 1
            assert handlers[0] == mock_handler

    def test_handler_fallback_on_import_or_init_exception(self) -> None:
        mock_client = MagicMock()

        with (
            patch("src.utils.observability.settings") as mock_settings,
            patch("src.utils.observability.get_langfuse_client", return_value=mock_client),
            patch(
                "langfuse.langchain.CallbackHandler", side_effect=Exception("Initialization failed")
            ),
        ):
            mock_settings.langfuse_public_key = "pk-test"
            mock_settings.langfuse_secret_key = "sk-test"

            handlers = get_langfuse_callback_handler()
            assert handlers == []

    def test_flush_langfuse_when_client_active(self) -> None:
        mock_client = MagicMock()
        with patch("src.utils.observability.get_langfuse_client", return_value=mock_client):
            flush_langfuse()
            mock_client.flush.assert_called_once()

    def test_flush_langfuse_handles_client_exception_gracefully(self) -> None:
        mock_client = MagicMock()
        mock_client.flush.side_effect = RuntimeError("Network timeout")
        with patch("src.utils.observability.get_langfuse_client", return_value=mock_client):
            # Should not raise exception
            flush_langfuse()
            mock_client.flush.assert_called_once()
