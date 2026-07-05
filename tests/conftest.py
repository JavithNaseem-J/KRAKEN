"""Root conftest — makes shared/ and services/ importable in all tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Project root on sys.path so tests can import shared.* and services.*
sys.path.insert(0, str(Path(__file__).parent.parent))
