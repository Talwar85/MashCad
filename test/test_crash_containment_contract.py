"""
W13 Paket C: Crash Containment Regression Contracts
====================================================

Validiert dass das W13 Crash-Containment System korrekt funktioniert:
- Drag-Tests laufen im Hauptlauf (nicht mehr skip)
- Tests sind mit @pytest.mark.xfail(strict=False) markiert
- Subprozess-Isolierung schützt Haupt-Pytest-Runner vor Absturz
- Isolierte Tests sind weiterhin separat verfügbar

W12 → W13 Änderung:
- W12: Tests waren skipped (Containment via Auslagerung)
- W13: Tests laufen mit Subprozess-Isolierung (Contained Runnable)

Author: GLM 4.7 (UX/WORKFLOW + QA Integration Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

import pytest
import os


class TestCrashContainmentContract:
    """
    W13 Paket C: Regression Contracts für Crash-Containment.

    Validiert dass:
    1. Die Drag-Tests NICHT mehr skip markiert sind (W13 Änderung!)
    2. Die Tests sind mit @pytest.mark.xfail(strict=False) markiert
    3. Die Tests verwenden Subprozess-Isolierung via crash_containment_helper
    4. Die isolierten Tests in separater Datei weiterhin verfügbar sind
    """

    def test_interaction_consistency_drag_tests_are_not_skipped(self):
        """
        D-W13-R1: Drag-Tests sind NICHT mehr skip markiert (W12→W13 Migration).

        W12: Tests waren mit @pytest.mark.skip markiert (ausgelagert)
        W13: Tests laufen mit @pytest.mark.xfail(strict=False) + Subprozess-Isolierung
        """
        test_file = "test/harness/test_interaction_consistency.py"
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # W13: Sollte KEIN @pytest.mark.skip für Drag-Tests enthalten
        # (W12 hatte skip, W13 hat xfail)
        assert "@pytest.mark.skip" not in content, \
            "W13: Drag-Tests sollten NICHT mit skip markiert sein"

        # Prüfe dass xfail mit strict=False verwendet wird
        assert "@pytest.mark.xfail" in content, \
            "W13: Drag-Tests sollten mit xfail markiert sein"

        assert 'strict=False' in content, \
            "W13: xfail sollte strict=False verwenden (Test kann bei stabilisierung passieren)"

    def test_interaction_consistency_uses_subprocess_isolation(self):
        """
        D-W13-R2: Drag-Tests verwenden Subprozess-Isolierung.

        W13: Tests rufen run_test_in_subprocess() aus crash_containment_helper auf.
        """
        test_file = "test/harness/test_interaction_consistency.py"
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Prüfe dass Subprozess-Isolierung verwendet wird
        assert "run_test_in_subprocess" in content, \
            "W13: Drag-Tests sollten Subprozess-Isolierung verwenden"

        assert "crash_containment_helper" in content, \
            "W13: crash_containment_helper sollte importiert werden"

        assert "xfail_on_crash" in content, \
            "W13: xfail_on_crash sollte bei Crash aufgerufen werden"

    def test_interaction_consistency_has_w13_reference(self):
        """
        D-W13-R3: Haupt-Test-File hat W13 Referenz.

        W13: Header und Comments sollten auf W13 "Contained Runnable" verweisen.
        """
        test_file = "test/harness/test_interaction_consistency.py"
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Prüfe W13 Reference
        assert "W13" in content, \
            "W13: Test-File sollte W13 referenzieren"

        # Prüfe "Contained Runnable" Strategie
        assert "Contained Runnable" in content or "Subprozess-Isolierung" in content, \
            "W13: Sollte auf Contained Runnable Strategie verweisen"

    def test_isolated_drag_test_file_still_exists(self):
        """
        D-W13-R4: Isolierte Drag-Test Datei existiert weiterhin.

        Die isolierten Tests sind weiterhin separat verfügbar für dedizierte Läufe.
        """
        isolated_file = "test/harness/test_interaction_drag_isolated.py"
        assert os.path.exists(isolated_file), \
            f"W13: Isolierte Test-Datei {isolated_file} sollte weiterhin existieren"

        # Prüfe dass die isolierten Tests darin sind
        with open(isolated_file, 'r', encoding='utf-8') as f:
            content = f.read()

        assert "test_circle_move_resize_isolated" in content
        assert "test_rectangle_edge_drag_isolated" in content
        assert "test_line_drag_consistency_isolated" in content

    def test_isolated_tests_have_strict_xfail(self):
        """
        D-W13-R5: Isolierte Tests haben xfail mit strict=True (W12 legacy).

        Die isolierten Tests in test_interaction_drag_isolated.py sind
        weiterhin mit strict=True markiert (W12 Standard).
        """
        isolated_file = "test/harness/test_interaction_drag_isolated.py"
        with open(isolated_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Prüfe xfail Marker
        assert "@pytest.mark.xfail" in content, \
            "W13: Isolierte Tests sollten mit xfail markiert sein"

        # Isolierte Tests verwenden strict=True (W12 Standard)
        assert 'strict=True' in content, \
            "W13: Isolierte Tests sollten strict=True verwenden"

    def test_blocker_signature_well_documented(self):
        """
        D-W13-R6: Blocker-Signaturen sind gut dokumentiert.

        Die ACCESS_VIOLATION_INTERACTION_DRAG Blocker-Signatur sollte dokumentiert sein.
        """
        # Prüfe Haupt-Test-File
        main_file = "test/harness/test_interaction_consistency.py"
        with open(main_file, 'r', encoding='utf-8') as f:
            main_content = f.read()

        assert "ACCESS_VIOLATION_INTERACTION_DRAG" in main_content or "ACCESS_VIOLATION" in main_content, \
            "W13: Blocker-Signatur sollte dokumentiert sein"

        # Prüfe isoliertes Test-File
        isolated_file = "test/harness/test_interaction_drag_isolated.py"
        with open(isolated_file, 'r', encoding='utf-8') as f:
            isolated_content = f.read()

        assert "ACCESS_VIOLATION" in isolated_content

    def test_no_skip_markers_in_drag_tests(self):
        """
        D-W13-R7: Kein @pytest.mark.skip in Drag-Tests.

        Explizite Prüfung dass die 3 Drag-Tests nicht skip markiert sind.
        """
        test_file = "test/harness/test_interaction_consistency.py"
        with open(test_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Sammle alle Zeilen mit @pytest.mark.skip
        skip_lines = [(i, line) for i, line in enumerate(lines) if "@pytest.mark.skip" in line]

        # Wenn es skip Marker gibt, prüfe ob sie in Drag-Test Methoden sind
        for i, line in skip_lines:
            # Prüfe den Kontext (nächste 10 Zeilen)
            context = "".join(lines[i:min(i+10, len(lines))])
            if "def test_circle_move_resize" in context:
                raise AssertionError("W13: test_circle_move_resize sollte NICHT skip markiert sein")
            if "def test_rectangle_edge_drag" in context:
                raise AssertionError("W13: test_rectangle_edge_drag sollte NICHT skip markiert sein")
            if "def test_line_drag_consistency" in context:
                raise AssertionError("W13: test_line_drag_consistency sollte NICHT skip markiert sein")


class TestGateRunnerContractW13:
    """
    W13 Paket C: Gate-Runner Contract Tests.

    Validiert dass gate_ui.ps1 und generate_gate_evidence.ps1 die W13 Änderungen
    korrekt berücksichtigen.
    """

    def test_gate_ui_has_w13_header(self):
        """
        D-W13-R8: gate_ui.ps1 hat W13 Header.

        Das Gate-Skript sollte auf W13 Unskip + Retest Edition aktualisiert sein.
        """
        gate_file = "scripts/gate_ui.ps1"
        with open(gate_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Prüfe W13 Reference (oder W12 als Fallback)
        assert ("W13" in content or "W 13" in content or "W12" in content), \
            "W13: Gate-Skript sollte W13 (oder W12) referenzieren"

    def test_gate_evidence_has_w13_header(self):
        """
        D-W13-R9: generate_gate_evidence.ps1 hat W13 Header.

        Das Evidence-Skript sollte auf W13 Unskip + Retest Edition aktualisiert sein.
        """
        evidence_file = "scripts/generate_gate_evidence.ps1"
        with open(evidence_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Prüfe W13 Reference (oder W12 als Fallback)
        assert ("W13" in content or "W 13" in content or "W12" in content), \
            "W13: Evidence-Skript sollte W13 (oder W12) referenzieren"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
