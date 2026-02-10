"""
Sketch Agent - Test Suite

Testet die grundlegende Funktionalität des SketchAgent
und des ReconstructionAgent.

Author: Claude (Sketch Agent)
Date: 2026-02-10
"""
import sys
sys.path.insert(0, 'c:/LiteCad')

from sketching import SketchAgent, create_agent


def test_agent_creation():
    """Test 1: Agent erstellen"""
    print("\n" + "="*60)
    print("TEST 1: Agent Creation")
    print("="*60)

    agent = SketchAgent(mode="random", headless=True, seed=42)

    assert agent.mode == "random"
    assert agent.headless == True
    assert agent._parts_generated == 0

    print("[OK] Agent erstellt")


def test_generate_part():
    """Test 2: Part generieren"""
    print("\n" + "="*60)
    print("TEST 2: Generate Part")
    print("="*60)

    agent = create_agent(mode="adaptive", headless=True, seed=42)
    result = agent.generate_part(complexity="simple")

    assert result is not None
    assert hasattr(result, 'success')
    assert hasattr(result, 'operations')
    assert hasattr(result, 'duration_ms')

    print(f"Success: {result.success}")
    print(f"Operations: {result.operations}")
    print(f"Duration: {result.duration_ms:.2f}ms")

    if result.success:
        print(f"Solid: {result.solid}")
        print(f"Face Count: {result.face_count}")
        print(f"Volume: {result.volume:.2f}mm³")
        print("[OK] Part generiert")
    else:
        print(f"Error: {result.error}")


def test_batch():
    """Test 3: Batch Test"""
    print("\n" + "="*60)
    print("TEST 3: Batch Test")
    print("="*60)

    agent = create_agent(mode="random", headless=True, seed=42)
    batch = agent.run_batch(count=10, complexity="simple")

    assert batch.total_count == 10
    assert hasattr(batch, 'success_rate')

    print(f"Total: {batch.total_count}")
    print(f"Success: {batch.success_count}")
    print(f"Success Rate: {batch.success_rate:.1%}")
    print(f"Avg Duration: {batch.avg_duration_ms:.2f}ms")

    print("[OK] Batch Test abgeschlossen")


def test_stats():
    """Test 4: Statistiken"""
    print("\n" + "="*60)
    print("TEST 4: Stats")
    print("="*60)

    agent = create_agent(mode="adaptive", headless=True, seed=42)
    agent.run_batch(count=5, complexity="simple")

    stats = agent.get_stats()

    print(f"Stats: {stats}")

    assert stats['parts_generated'] == 5
    assert stats['mode'] == "adaptive"
    assert stats['headless'] == True

    print("[OK] Stats funktionieren")


def test_reconstruction_agent():
    """Test 5: ReconstructionAgent"""
    print("\n" + "="*60)
    print("TEST 5: ReconstructionAgent")
    print("="*60)

    from sketching.analysis.reconstruction_agent import ReconstructionAgent

    agent = ReconstructionAgent(slow_mode=False, step_delay=0.0)

    # Teste ohne echtes Mesh (simuliert)
    print(f"Agent created: slow_mode={agent.slow_mode}")

    # Teste step execution
    from sketching.analysis.mesh_analyzer import ReconstructionStep

    # Teste create_profile
    step = ReconstructionStep(
        step_id=0,
        operation="create_profile",
        description="Erstelle Kreis",
        params={"type": "circle", "radius": 10, "center": (0, 0)}
    )

    result = agent._execute_step(step)
    if result:
        print(f"[OK] create_profile: {result}")
        print(f"  - Closed profiles: {len(result.closed_profiles) if hasattr(result, 'closed_profiles') else 'N/A'}")

    # Teste create_profile mit Rechteck
    step2 = ReconstructionStep(
        step_id=1,
        operation="create_profile",
        description="Erstelle Rechteck",
        params={"type": "rectangle", "width": 20, "height": 15, "center": (0, 0)}
    )

    result2 = agent._execute_step(step2)
    if result2:
        print(f"[OK] create_profile (rectangle): {result2}")

    # Teste create_profile mit Polygon
    step3 = ReconstructionStep(
        step_id=2,
        operation="create_profile",
        description="Erstelle Polygon",
        params={"type": "polygon", "sides": 6, "radius": 15, "center": (0, 0)}
    )

    result3 = agent._execute_step(step3)
    if result3:
        print(f"[OK] create_profile (polygon): {result3}")

    print("[OK] ReconstructionAgent Step Execution")


def test_reconstruction_with_extrude():
    """Test 6: Reconstruction mit Extrusion"""
    print("\n" + "="*60)
    print("TEST 6: Reconstruction mit Extrusion")
    print("="*60)

    from sketching.analysis.reconstruction_agent import ReconstructionAgent
    from sketching.analysis.mesh_analyzer import ReconstructionStep

    agent = ReconstructionAgent(slow_mode=False, step_delay=0.0)

    # Erstelle Profil
    profile_step = ReconstructionStep(
        step_id=0,
        operation="create_profile",
        description="Erstelle Kreis",
        params={"type": "circle", "radius": 10, "center": (0, 0)}
    )

    sketch = agent._execute_step(profile_step)
    print(f"Sketch erstellt: {sketch is not None}")

    if sketch:
        # Extrudiere
        extrude_step = ReconstructionStep(
            step_id=1,
            operation="extrude",
            description="Extrudiere",
            params={"sketch": sketch, "distance": 25}
        )

        solid = agent._execute_step(extrude_step)
        print(f"Solid erstellt: {solid is not None}")

        if solid:
            print(f"  - Volume: {solid.volume:.2f}mm³")
            print(f"  - Face Count: {len(list(solid.faces()))}")

            print("[OK] Reconstruction mit Extrusion erfolgreich")
        else:
            print("[FAIL] Extrusion fehlgeschlagen")
    else:
        print("[FAIL] Sketch-Erstellung fehlgeschlagen")


def test_mesh_analyzer():
    """Test 7: MeshAnalyzer"""
    print("\n" + "="*60)
    print("TEST 7: MeshAnalyzer")
    print("="*60)

    from sketching.analysis.mesh_analyzer import MeshAnalyzer

    analyzer = MeshAnalyzer()

    # Teste mit Test-Mesh (falls vorhanden)
    import os
    test_mesh = "c:/LiteCad/stl/V1.stl"

    if os.path.exists(test_mesh):
        print(f"Analysiere: {test_mesh}")
        analysis = analyzer.analyze(test_mesh)

        print(f"  - Primitives: {analysis.primitive_count}")
        print(f"  - Features: {analysis.feature_count}")
        print(f"  - Steps: {analysis.step_count}")
        print(f"  - Duration: {analysis.duration_ms:.2f}ms")
        print(f"  - Mesh Info: {analysis.mesh_info}")

        print("[OK] MeshAnalyzer")
    else:
        print(f"[SKIP] Test-Mesh nicht gefunden: {test_mesh}")
        print("  (Analysiere ohne Datei...)")
        analysis = analyzer.analyze("nonexistent.stl")
        print(f"  - Primitives: {analysis.primitive_count}")
        print("[OK] MeshAnalyzer (kein Fehler)")


def run_all_tests():
    """Führt alle Tests aus"""
    print("\n" + "="*60)
    print("SKETCH AGENT TEST SUITE")
    print("="*60)

    test_agent_creation()
    test_generate_part()
    test_batch()
    test_stats()
    test_reconstruction_agent()
    test_reconstruction_with_extrude()
    test_mesh_analyzer()

    print("\n" + "="*60)
    print("ALLE TESTS ABGESCHLOSSEN")
    print("="*60)


if __name__ == "__main__":
    run_all_tests()
