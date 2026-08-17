"""Root conftest — puts the repository root on sys.path so tests import ``src.*``.

KRAKEN is a consolidated single-process application: every subsystem lives under
the ``src/`` package (``src/api`` gateway + sub-apps, ``src/agent`` graph,
``src/utils`` shared infrastructure). Unit tests run fully offline with mocks;
integration tests (``tests/integration``) boot the real consolidated app with
fakeredis/in-memory fallbacks and are gated behind the ``integration`` marker.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Project root on sys.path so tests can import shared.* and services.*
sys.path.insert(0, str(Path(__file__).parent.parent))
