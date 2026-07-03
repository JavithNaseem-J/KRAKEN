"""
Shared exception hierarchy for all AKEA services.
All custom exceptions inherit from AKEABaseException so callers can
catch the base class without knowing the exact subtype.
"""
from __future__ import annotations


class AKEABaseException(Exception):
    """Root exception for all AKEA errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, details={self.details})"


# ── Knowledge ─────────────────────────────────────────────────────────────────
class KnowledgeRetrievalError(AKEABaseException):
    """Raised when retrieval from any knowledge source fails."""


class KnowledgeIngestionError(AKEABaseException):
    """Raised when ingesting documents into the vector store fails."""


# ── Action / Write Safety ─────────────────────────────────────────────────────
class ActionExecutionError(AKEABaseException):
    """Raised when an action fails during execution."""


class PathTraversalError(AKEABaseException):
    """Raised when a write target escapes the allowed workspace directory."""


class InvalidExtensionError(AKEABaseException):
    """Raised when a write target has a disallowed file extension."""


class ActionNotFoundError(AKEABaseException):
    """Raised when the requested action name is not in the registry."""


# ── Agent / Orchestration ─────────────────────────────────────────────────────
class AgentError(AKEABaseException):
    """Base for all agent orchestration errors."""


class PlanningError(AgentError):
    """Raised when the planner node fails to decompose a request."""


class ReasoningError(AgentError):
    """Raised when the reasoner node fails to analyse retrieved chunks."""


class DecisionError(AgentError):
    """Raised when the decider node cannot select a valid action."""


# ── Approval / HITL ───────────────────────────────────────────────────────────
class ApprovalTimeoutError(AKEABaseException):
    """Raised when a HITL approval request expires without a decision."""


class ApprovalRejectedError(AKEABaseException):
    """Raised when a human explicitly rejects an action."""


# ── Memory ────────────────────────────────────────────────────────────────────
class MemoryReadError(AKEABaseException):
    """Raised when reading from short-term or long-term memory fails."""


class MemoryWriteError(AKEABaseException):
    """Raised when writing to memory fails."""


# ── Audit ─────────────────────────────────────────────────────────────────────
class AuditWriteError(AKEABaseException):
    """Raised when writing an audit log entry fails."""


# ── Gateway ───────────────────────────────────────────────────────────────────
class RateLimitError(AKEABaseException):
    """Raised when a client exceeds the configured request rate."""


class AuthenticationError(AKEABaseException):
    """Raised when an API key is missing or invalid."""
