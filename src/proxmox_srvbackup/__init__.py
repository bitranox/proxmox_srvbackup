"""Public package surface exposing greeting, metadata, and configuration.

This module provides the stable public API for the package, routing imports
through the proper architectural layers:
- Domain exports: Core business logic (greeting)
- Composition exports: Wired adapter services (configuration)
- Metadata: Package information
"""

from __future__ import annotations

# Metadata
from .__init__conf__ import print_info

# Composition exports (wired adapters)
from .composition import get_config

# Domain exports
from .domain.behaviors import (
    CANONICAL_GREETING,
    build_greeting,
)

__all__ = [
    "CANONICAL_GREETING",
    "build_greeting",
    "get_config",
    "print_info",
]
