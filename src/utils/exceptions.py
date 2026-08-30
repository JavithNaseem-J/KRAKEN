from __future__ import annotations


class KRAKENBaseException(Exception):  # noqa: N818
    """Root exception for all KRAKEN errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, details={self.details})"


# Action / Write Safety
class ActionExecutionError(KRAKENBaseException):
    """Raised when an action fails during execution."""


class PathTraversalError(KRAKENBaseException):
    """Raised when a write target escapes the allowed workspace directory."""


class InvalidExtensionError(KRAKENBaseException):
    """Raised when a write target has a disallowed file extension."""


class ActionNotFoundError(KRAKENBaseException):
    """Raised when the requested action name is not in the registry."""


class EmbeddingProviderUnavailableError(KRAKENBaseException):
    """Raised when no configured embedding provider can produce real vectors."""


class LLMProviderUnavailableError(KRAKENBaseException):
    """Raised when the configured LLM provider is unavailable or circuit-open."""
