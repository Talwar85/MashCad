"""
Phase 5: OCP-First Shell/Hollow Integration Tests

OCP-First Migration Phase F (Feb 2026):
=======================================
Die OCP-First Helper-Klassen für Shell und Hollow wurden entfernt.
Die Funktionalität ist jetzt direkt in Body._compute_shell() implementiert
mit BRepOffsetAPI_MakeThickSolid.

- Shell/Hollow: BRepOffsetAPI_MakeThickSolid (Phase F)

Tests für diese Operationen sollten jetzt als Integration-Tests der Body-Klasse
geschrieben werden, die die kompletten Features testen.

Dieser Test-File ist OBSOLET und wird nicht mehr verwendet.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="OCP-First Migration Phase F abgeschlossen: Helper-Klassen entfernt, Tests obsolet"
)


class TestOCPFirstShellHollow:
    """Stub-Klasse - siehe Docstring oben."""

    def test_obsolete(self):
        """Dieser Test ist obsolet nach OCP-First Migration."""
        assert True
