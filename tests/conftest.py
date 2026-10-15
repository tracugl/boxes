"""Shared pytest setup.

The Hexmo generators open with the HO README's settings
(``boxes/generators/_hexmo_defaults.py``).  Most Hexmo tests check one
feature at a time against the generators' original defaults (the boxes-style
hole patterns, labels, no track jigs, an automatic under-track height, ...),
and their pinned drawings were made with those.  So the HO defaults are
switched off for the whole run (before any module- or class-scoped fixture
builds a generator), and switched back on only for tests marked
``ho_defaults`` (tests/test_hexmo_defaults.py), which check them.
"""
from __future__ import annotations

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "ho_defaults: run with the Hexmo generators' HO defaults switched on")


@pytest.fixture(scope="session", autouse=True)
def _original_hexmo_defaults():
    """Switch the Hexmo HO defaults off for the session.

    @returns The HO defaults as they were, ``(hexmo, rectangle)``, for
             :func:`_ho_defaults_when_marked` to put back.
    """
    from boxes.generators import _hexmo_defaults
    saved = (_hexmo_defaults.HO_DEFAULTS, _hexmo_defaults.HO_RECTANGLE_DEFAULTS)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(_hexmo_defaults, "HO_DEFAULTS", {})
        patch.setattr(_hexmo_defaults, "HO_RECTANGLE_DEFAULTS", {})
        yield saved


@pytest.fixture(autouse=True)
def _ho_defaults_when_marked(request, monkeypatch, _original_hexmo_defaults):
    """For a test marked ``ho_defaults``, switch the HO defaults back on."""
    if not request.node.get_closest_marker("ho_defaults"):
        return
    from boxes.generators import _hexmo_defaults
    hexmo, rectangle = _original_hexmo_defaults
    monkeypatch.setattr(_hexmo_defaults, "HO_DEFAULTS", hexmo)
    monkeypatch.setattr(_hexmo_defaults, "HO_RECTANGLE_DEFAULTS", rectangle)
