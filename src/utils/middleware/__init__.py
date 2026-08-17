"""
Shared FastAPI middleware package.
"""

from src.utils.middleware.rate_limit import RateLimitMiddleware

__all__ = ["RateLimitMiddleware"]
