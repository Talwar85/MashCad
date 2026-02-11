"""
Test: Sketch Agent - Basisfunktionen
Prüft ob der SketchAgent korrekt importiert und headless Parts generieren kann.
"""

import sys
import os

# Pfad zu LiteCad hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

def test_import():
    """Test 1: Import check"""
    logger.info("=" * 50)
    logger.info("TEST 1: Sketch Agent Import")
    logger.info("=" * 50)

    try:
        from sketching import SketchAgent, create_agent
        logger.success("SketchAgent import erfolgreich")
        return True
    except Exception as e:
        logger.error(f"Import fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_headless_generation():
    """Test 2: Headless Part-Generierung"""
    logger.info("=" * 50)
    logger.info("TEST 2: Headless Part-Generierung")
    logger.info("=" * 50)

    try:
        from sketching import create_agent

        # Agent ohne Document (headless)
        agent = create_agent(
            document=None,
            mode="adaptive",
            headless=True,
            seed=42
        )
        logger.info(f"Agent erstellt: {agent.get_stats()}")

        # Part generieren
        result = agent.generate_part(complexity="simple")

        if result.success:
            logger.success(f"Part generiert!")
            logger.info(f"  Operations: {result.operations}")
            logger.info(f"  Duration: {result.duration_ms:.1f}ms")
            if result.solid:
                logger.info(f"  Solid: {type(result.solid)}")
            return True
        else:
            logger.error(f"Generierung fehlgeschlagen: {result.error}")
            return False

    except Exception as e:
        logger.error(f"Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_document_integration():
    """Test 3: Document-Integration (wenn verfügbar)"""
    logger.info("=" * 50)
    logger.info("TEST 3: Document-Integration")
    logger.info("=" * 50)

    try:
        from sketching import create_agent
        from modeling import Document

        # Document erstellen
        doc = Document("Test_Document")
        logger.info(f"Document erstellt: {doc.name}")

        # Agent MIT Document
        agent = create_agent(
            document=doc,
            mode="adaptive",
            headless=True,
            seed=42
        )
        logger.info(f"Agent mit Document erstellt")

        # Part generieren (sollte Sketch im Browser erstellen)
        result = agent.generate_part(complexity="simple")

        if result.success:
            logger.success(f"Part generiert!")
            logger.info(f"  Operations: {result.operations}")
            logger.info(f"  Sketch Count: {result.sketch_count}")

            # Prüfen ob Sketch im Document
            if doc.sketches:
                logger.success(f"Sketch im Document: {len(doc.sketches)} Sketch(es)")
                for sk in doc.sketches:
                    logger.info(f"  - {sk.name}")
            else:
                logger.warning("Keine Sketches im Document gefunden!")

            # Prüfen ob Body im Document
            if doc.bodies:
                logger.success(f"Body im Document: {len(doc.bodies)} Body(s)")
                for body in doc.bodies:
                    logger.info(f"  - {body.name}")
            else:
                logger.warning("Keine Bodies im Document gefunden!")

            return True
        else:
            logger.error(f"Generierung fehlgeschlagen: {result.error}")
            return False

    except Exception as e:
        logger.error(f"Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_complexity_levels():
    """Test 4: Komplexitätsstufen (n-Sketches)"""
    logger.info("=" * 50)
    logger.info("TEST 4: Komplexitätsstufen (n-Sketches)")
    logger.info("=" * 50)

    try:
        from sketching import create_agent
        from modeling import Document

        results = []

        for complexity in ["simple", "medium", "complex"]:
            logger.info(f"Testing complexity: {complexity}")

            # Neues Document für jeden Test
            doc = Document(f"Test_{complexity}")
            agent = create_agent(
                document=doc,
                mode="adaptive",
                headless=True,
                seed=42  # Gleicher Seed für reproduzierbare Ergebnisse
            )

            result = agent.generate_part(complexity=complexity)

            if result.success:
                logger.success(f"  {complexity}: {len(doc.sketches)} Sketches, {len(doc.bodies)} Body(s)")
                logger.info(f"    Operations: {result.operations}")
                results.append((complexity, True, len(doc.sketches)))
            else:
                logger.error(f"  {complexity}: FAILED - {result.error}")
                results.append((complexity, False, 0))

        # Check: n-Sketches implemented?
        all_passed = all(r[1] for r in results)
        if all_passed:
            logger.success("Alle Komplexitätsstufen bestanden!")

            # Prüfe ob n-Sketches implementiert
            simple_sketches = next((r[2] for r in results if r[0] == "simple"), 0)
            medium_sketches = next((r[2] for r in results if r[0] == "medium"), 0)
            complex_sketches = next((r[2] for r in results if r[0] == "complex"), 0)

            logger.info(f"Sketch Count: simple={simple_sketches}, medium={medium_sketches}, complex={complex_sketches}")

        return all_passed

    except Exception as e:
        logger.error(f"Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    results = []

    # Test 1: Import
    results.append(("Import", test_import()))

    # Test 2: Headless
    results.append(("Headless", test_headless_generation()))

    # Test 3: Document Integration
    results.append(("Document", test_document_integration()))

    # Test 4: Complexity Levels (n-Sketches)
    results.append(("Complexity", test_complexity_levels()))

    # Summary
    logger.info("=" * 50)
    logger.info("TEST SUMMARY")
    logger.info("=" * 50)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        logger.info(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    if all_passed:
        logger.success("Alle Tests bestanden!")
        sys.exit(0)
    else:
        logger.error("Einige Tests fehlgeschlagen!")
        sys.exit(1)
