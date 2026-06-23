"""Behaviour-layer stories: pure domain function tests."""

from __future__ import annotations

import pytest

from proxmox_srvbackup.domain import behaviors


@pytest.mark.os_agnostic
def test_build_greeting_returns_canonical_text() -> None:
    """Verify build_greeting returns the canonical greeting string."""
    assert behaviors.build_greeting() == "Hello World"
