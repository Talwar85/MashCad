"""
Visual MeshConverter Comparison Test
====================================

Vergleicht alle 3 MeshConverter (Simple, Current, Perfect) visuell:
- Original Mesh (grau)
- Simple BREP (rot)
- Current BREP (grün)
- Perfect BREP (blau)

Zeigt Face-Count und Qualität metrischen an.

Author: Claude (MeshConverter Architecture)
Date: 2026-02-10
"""

import sys
sys.path.insert(0, 'c:/LiteCad')

import pyvista as pv
from meshconverter import (
    SimpleConverter,
    CurrentConverter, CurrentMode,
    PerfectConverter, HAS_PERFECT_CONVERTER,
    convert_simple, convert_v10
)
from loguru import logger


class VisualComparator:
    """
    Visueller Vergleich der 3 MeshConverter.

    Erstellt 4 Viewports nebeneinander:
    1. Original Mesh
    2. SimpleConverter Ergebnis
    3. CurrentConverter Ergebnis
    4. PerfectConverter Ergebnis
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.mesh = None
        self.results = {}

    def load_mesh(self):
        """Lädt das STL Mesh."""
        logger.info(f"Lade {self.filepath}...")
        self.mesh = pv.read(self.filepath)
        logger.info(f"  {self.mesh.n_points} Punkte, {self.mesh.n_cells} Faces")
        return self.mesh

    def run_all_converters(self):
        """Führt alle 3 Converter aus."""
        if self.mesh is None:
            self.load_mesh()

        print("\n" + "="*60)
        print("MESHCONVERTER VERGLEICH - " + self.filepath)
        print("="*60)

        # SimpleConverter
        print("\n[1/3] SimpleConverter...")
        self.results['simple'] = self._run_simple()

        # CurrentConverter (V10)
        print("\n[2/3] CurrentConverter (V10)...")
        self.results['current_v10'] = self._run_current_v10()

        # CurrentConverter (Final)
        print("\n[3/4] CurrentConverter (Final)...")
        self.results['current_final'] = self._run_current_final()

        # PerfectConverter
        if HAS_PERFECT_CONVERTER:
            print("\n[4/4] PerfectConverter...")
            self.results['perfect'] = self._run_perfect()
        else:
            print("\n[4/4] PerfectConverter... SKIPPED (nicht verfügbar)")
            self.results['perfect'] = None

        return self.results

    def _run_simple(self):
        """Führt SimpleConverter aus."""
        converter = SimpleConverter()

        def on_progress(update):
            if update.progress >= 1.0 or update.progress % 0.2 < 0.05:
                print(f"  [{update.phase.value}] {update.progress*100:.0f}% - {update.message}")

        result = converter.convert_async(self.mesh, on_progress)

        print(f"  -> Status: {result.status.value if result.status else 'N/A'}")
        print(f"  -> Face-Count: {result.face_count}")

        return result

    def _run_current_v10(self):
        """Führt CurrentConverter V10 aus."""
        converter = CurrentConverter(mode=CurrentMode.V10)

        def on_progress(update):
            if update.progress >= 1.0 or update.progress % 0.2 < 0.05:
                print(f"  [{update.phase.value}] {update.progress*100:.0f}% - {update.message}")

        result = converter.convert_async(self.mesh, on_progress)

        print(f"  -> Status: {result.status.value if result.status else 'N/A'}")
        print(f"  -> Face-Count: {result.face_count}")

        return result

    def _run_current_final(self):
        """Führt CurrentConverter Final aus."""
        converter = CurrentConverter(mode=CurrentMode.FINAL)

        def on_progress(update):
            if update.progress >= 1.0 or update.progress % 0.2 < 0.05:
                print(f"  [{update.phase.value}] {update.progress*100:.0f}% - {update.message}")

        result = converter.convert_async(self.mesh, on_progress)

        print(f"  -> Status: {result.status.value if result.status else 'N/A'}")
        print(f"  -> Face-Count: {result.face_count}")

        return result

    def _run_perfect(self):
        """Führt PerfectConverter aus."""
        converter = PerfectConverter()

        def on_progress(update):
            if update.progress >= 1.0 or update.progress % 0.2 < 0.05:
                print(f"  [{update.phase.value}] {update.progress*100:.0f}% - {update.message}")

        result = converter.convert_async(self.mesh, on_progress)

        print(f"  -> Status: {result.status.value if result.status else 'N/A'}")
        print(f"  -> Face-Count: {result.face_count}")

        return result

    def print_summary(self):
        """Druckt Zusammenfassung der Ergebnisse."""
        print("\n" + "="*60)
        print("ERGEBNIS-ZUSAMMENFASSUNG")
        print("="*60)

        print(f"{'Converter':<20} {'Faces':>10} {'Status':>15}")
        print("-"*60)

        for name, result in self.results.items():
            if result is None:
                continue
            status = result.status.value if result.status else "N/A"
            print(f"{name:<20} {result.face_count:>10} {status:>15}")

        # Besten Converter ermitteln (wenigste Faces)
        valid_results = {k: v for k, v in self.results.items() if v and v.face_count > 0}
        if valid_results:
            best = min(valid_results.items(), key=lambda x: x[1].face_count)
            print(f"\n* Beste Face-Count: {best[0]} ({best[1].face_count} Faces)")

    def visualize(self):
        """Zeigt visuellen Vergleich in PyVista."""
        pl = pv.Plotter(shape=(1, 4))
        pl.set_background("#2d2d30")

        # 1. Original Mesh
        pl.subplot(0, 0)
        pl.add_mesh(self.mesh, color="#888888", show_edges=True)
        pl.add_text(f"Original\n{self.mesh.n_cells} Faces", font_size=12)

        # 2. SimpleConverter
        pl.subplot(0, 1)
        result = self.results.get('simple')
        if result and result.solid:
            # Extrahiere VTK Mesh aus Solid
            try:
                solid_mesh = result.solid.mesh
                pl.add_mesh(solid_mesh, color="#c42b1c", show_edges=True, edge_color="#ffffff")
                pl.add_text(f"Simple\n{result.face_count} Faces", font_size=12)
            except:
                pl.add_text("Simple\nNo Mesh", font_size=12)
        else:
            pl.add_text("Simple\nFailed", font_size=12)

        # 3. CurrentConverter V10
        pl.subplot(0, 2)
        result = self.results.get('current_v10')
        if result and result.solid:
            try:
                solid_mesh = result.solid.mesh
                pl.add_mesh(solid_mesh, color="#4ec9b0", show_edges=True, edge_color="#ffffff")
                pl.add_text(f"Current V10\n{result.face_count} Faces", font_size=12)
            except:
                pl.add_text("Current V10\nNo Mesh", font_size=12)
        else:
            pl.add_text("Current V10\nFailed", font_size=12)

        # 4. PerfectConverter
        pl.subplot(0, 3)
        result = self.results.get('perfect')
        if result and result.solid:
            try:
                solid_mesh = result.solid.mesh
                pl.add_mesh(solid_mesh, color="#569cd6", show_edges=True, edge_color="#ffffff")
                pl.add_text(f"Perfect\n{result.face_count} Faces", font_size=12)
            except:
                pl.add_text("Perfect\nNo Mesh", font_size=12)
        else:
            pl.add_text("Perfect\nFailed", font_size=12)

        pl.link_views()
        pl.show()


def test_v1_stl():
    """Test mit V1.stl"""
    comparator = VisualComparator("stl/V1.stl")
    comparator.load_mesh()
    comparator.run_all_converters()
    comparator.print_summary()

    # Uncomment für visuellen Vergleich
    # comparator.visualize()


def test_tensionmeter():
    """Test mit TensionMeter.stl (grössere Datei)"""
    comparator = VisualComparator("stl/TensionMeter.stl")
    comparator.load_mesh()
    comparator.run_all_converters()
    comparator.print_summary()

    # Uncomment für visuellen Vergleich
    # comparator.visualize()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Vergleiche MeshConverter visuell")
    parser.add_argument("file", nargs="?", default="stl/V1.stl",
                        help="STL Datei zum Testen")
    parser.add_argument("--visual", action="store_true",
                        help="Zeige visuellen Vergleich in PyVista")

    args = parser.parse_args()

    comparator = VisualComparator(args.file)
    comparator.load_mesh()
    comparator.run_all_converters()
    comparator.print_summary()

    if args.visual:
        comparator.visualize()
