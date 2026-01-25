"""
MashCad - Mesh-zu-BREP Konverter V10
====================================

Produktionsreifer Konverter, der STL/OBJ/PLY-Dateien in voll editierbare
BREP-Bodies umwandelt.

Features:
- Robustes Mesh-Laden mit Auto-Repair
- Intelligente Oberflächenerkennung (Planes, Cylinder, Spheres, Cones, NURBS)
- Topology-Preserving Mode (optional)
- Strukturierte Result-Types (Fail-Fast)

Keine externen Dependencies außer PyVista, scipy, sklearn, OCP/build123d.
KEIN pyransac3d - eigene Fitting-Algorithmen.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List, Dict, Tuple, Any
import numpy as np
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False
    logger.warning("PyVista nicht verfügbar")

try:
    from build123d import Solid, Shell, Shape
    HAS_BUILD123D = True
except ImportError:
    HAS_BUILD123D = False
    logger.warning("build123d nicht verfügbar")


# =============================================================================
# Result Types (Fail-Fast Pattern)
# =============================================================================

class ConversionStatus(Enum):
    """Status der Mesh-zu-BREP Konvertierung."""
    SUCCESS = auto()        # Vollständig konvertiert, wasserdicht
    PARTIAL = auto()        # Einige Flächen nicht erkannt
    SHELL_ONLY = auto()     # Nicht wasserdicht (Shell statt Solid)
    FAILED = auto()         # Konvertierung fehlgeschlagen


class LoadStatus(Enum):
    """Status des Mesh-Ladens."""
    SUCCESS = auto()        # Erfolgreich geladen und repariert
    REPAIRED = auto()       # Geladen mit Reparaturen
    FAILED = auto()         # Laden fehlgeschlagen


@dataclass
class LoadResult:
    """Ergebnis des Mesh-Ladens."""
    status: LoadStatus
    mesh: Optional['pv.PolyData'] = None
    message: str = ""
    repairs: List[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


@dataclass
class ConversionResult:
    """Ergebnis der Mesh-zu-BREP Konvertierung."""
    status: ConversionStatus
    solid: Optional[Any] = None  # Solid, Shell, oder Shape
    message: str = ""
    stats: dict = field(default_factory=dict)
    # stats: {"faces_detected": 12, "faces_converted": 10, "coverage": 0.92, ...}


@dataclass
class Region:
    """Eine segmentierte Region im Mesh."""
    region_id: int
    cell_ids: np.ndarray        # Indices der Mesh-Cells in dieser Region
    normal: np.ndarray          # Durchschnittliche Normale
    centroid: np.ndarray        # Schwerpunkt
    area: float                 # Gesamtfläche in mm²
    boundary_points: Optional[np.ndarray] = None  # Geordnete Randpunkte


@dataclass
class DetectedPrimitive:
    """Ein erkanntes geometrisches Primitiv."""
    type: str                   # "plane", "cylinder", "sphere", "cone", "bspline"
    region_id: int              # ID der zugehörigen Region
    params: dict                # Typ-spezifische Parameter
    boundary_points: np.ndarray # 3D Boundary-Punkte (geordnet)
    area: float                 # Fläche in mm²
    confidence: float           # 0-1, Fit-Qualität (1 - normalized_error)
    error: float                # Durchschnittlicher Fitting-Fehler in mm


# =============================================================================
# Mesh Loader & Repair
# =============================================================================

class MeshLoader:
    """
    Robustes Mesh-Laden mit Auto-Repair.

    Unterstützte Formate: STL, OBJ, PLY, VTK
    """

    @staticmethod
    def load(filepath: str, repair: bool = True) -> LoadResult:
        """
        Lädt Mesh-Datei mit optionaler automatischer Reparatur.

        Args:
            filepath: Pfad zur Mesh-Datei
            repair: Auto-Repair aktivieren (default: True)

        Returns:
            LoadResult mit Status, Mesh und Reparatur-Details
        """
        if not HAS_PYVISTA:
            return LoadResult(
                status=LoadStatus.FAILED,
                message="PyVista nicht installiert"
            )

        repairs = []
        stats = {}

        # 1. Datei laden
        try:
            mesh = pv.read(filepath)
            logger.info(f"Mesh geladen: {filepath}")
            stats['original_points'] = mesh.n_points
            stats['original_cells'] = mesh.n_cells
        except Exception as e:
            return LoadResult(
                status=LoadStatus.FAILED,
                message=f"Datei konnte nicht geladen werden: {e}"
            )

        if mesh.n_cells == 0:
            return LoadResult(
                status=LoadStatus.FAILED,
                message="Mesh enthält keine Faces"
            )

        if not repair:
            return LoadResult(
                status=LoadStatus.SUCCESS,
                mesh=mesh,
                stats=stats
            )

        # 2. Reparatur-Pipeline
        try:
            mesh, repairs = MeshLoader._repair_mesh(mesh)
            stats['final_points'] = mesh.n_points
            stats['final_cells'] = mesh.n_cells
            stats['repairs_applied'] = len(repairs)

            status = LoadStatus.REPAIRED if repairs else LoadStatus.SUCCESS

            logger.info(f"Mesh nach Repair: {mesh.n_points} Punkte, {mesh.n_cells} Faces")
            if repairs:
                logger.info(f"Reparaturen: {', '.join(repairs)}")

            return LoadResult(
                status=status,
                mesh=mesh,
                repairs=repairs,
                stats=stats
            )

        except Exception as e:
            logger.error(f"Mesh-Reparatur fehlgeschlagen: {e}")
            return LoadResult(
                status=LoadStatus.FAILED,
                message=f"Reparatur fehlgeschlagen: {e}"
            )

    @staticmethod
    def _repair_mesh(mesh: 'pv.PolyData') -> Tuple['pv.PolyData', List[str]]:
        """
        Führt Reparatur-Pipeline aus.

        Reparatur-Schritte:
        1. Triangulieren (falls nötig)
        2. Duplikate entfernen (clean)
        3. Degenerierte Faces entfernen (Area < 1e-10)
        4. Normalen konsistent machen
        5. Non-Manifold Edges behandeln (optional)
        """
        repairs = []

        # 1. Triangulieren
        if not mesh.is_all_triangles:
            mesh = mesh.triangulate()
            repairs.append("triangulated")
            logger.debug("Mesh trianguliert")

        # 2. Duplikate entfernen
        n_before = mesh.n_points
        mesh = mesh.clean(tolerance=1e-6)
        if mesh.n_points < n_before:
            repairs.append(f"removed {n_before - mesh.n_points} duplicate points")
            logger.debug(f"{n_before - mesh.n_points} duplizierte Punkte entfernt")

        # 3. Degenerierte Faces entfernen
        mesh, n_removed = MeshLoader._remove_degenerate_faces(mesh)
        if n_removed > 0:
            repairs.append(f"removed {n_removed} degenerate faces")
            logger.debug(f"{n_removed} degenerierte Faces entfernt")

        # 4. Normalen berechnen
        if 'Normals' not in mesh.cell_data:
            mesh.compute_normals(cell_normals=True, point_normals=True, inplace=True)
            repairs.append("computed normals")
            logger.debug("Normalen berechnet")

        # 5. Normalen-Konsistenz prüfen (optional - kann teuer sein)
        # TODO: Implement consistent normal orientation if needed

        return mesh, repairs

    @staticmethod
    def _remove_degenerate_faces(mesh: 'pv.PolyData', min_area: float = 1e-10) -> Tuple['pv.PolyData', int]:
        """
        Entfernt degenerierte Faces mit Area < min_area.

        Returns:
            (cleaned_mesh, number_of_removed_faces)
        """
        try:
            # compute_cell_sizes gibt ein neues Mesh mit 'Area' Feld zurück
            sized = mesh.compute_cell_sizes(area=True, length=False, volume=False)
            areas = sized.cell_data['Area']

            valid_mask = areas > min_area
            n_invalid = np.sum(~valid_mask)

            if n_invalid == 0:
                return mesh, 0

            # Nur gültige Cells extrahieren
            valid_indices = np.where(valid_mask)[0]
            cleaned = mesh.extract_cells(valid_indices)

            return cleaned, int(n_invalid)

        except Exception as e:
            logger.warning(f"Fehler beim Entfernen degenerierter Faces: {e}")
            return mesh, 0


# =============================================================================
# Main Converter Class
# =============================================================================

class MeshToBREPConverterV10:
    """
    Mesh-zu-BREP Konverter V10.

    Konvertiert PyVista Mesh zu Build123d Solid mit intelligenter
    Oberflächenerkennung.

    Usage:
        converter = MeshToBREPConverterV10()
        result = converter.convert("part.stl")
        if result.status == ConversionStatus.SUCCESS:
            solid = result.solid
    """

    def __init__(
        self,
        angle_tolerance: float = 5.0,       # Grad - für Normalen-Clustering
        fitting_tolerance: float = 0.5,     # mm - für Primitiv-Fitting
        sewing_tolerance: float = 0.5,      # mm - für Sewing (erhöht für besseres Matching)
        max_sewing_tolerance: float = 5.0,  # mm - Maximum für Multi-Pass Sewing (erhöht für komplexe Meshes)
        min_region_faces: int = 1,          # Minimum Faces pro Region (1 für kleine Meshes)
        preserve_topology: bool = False,    # Topology-Preserving Mode
        enable_nurbs: bool = True           # NURBS für organische Formen
    ):
        """
        Args:
            angle_tolerance: Winkeltoleranz für Normalen-Clustering (Grad)
            fitting_tolerance: Toleranz für Primitiv-Fitting (mm)
            sewing_tolerance: Toleranz für Face-Sewing (mm)
            max_sewing_tolerance: Maximum Toleranz für Multi-Pass Sewing (mm)
            min_region_faces: Minimum Faces um als Region zu gelten
            preserve_topology: Mesh-Topologie erhalten
            enable_nurbs: NURBS-Fitting für organische Formen aktivieren
        """
        self.angle_tol = angle_tolerance
        self.fitting_tol = fitting_tolerance
        self.sewing_tol = sewing_tolerance
        self.max_sewing_tol = max_sewing_tolerance
        self.min_region_faces = min_region_faces
        self.preserve_topology = preserve_topology
        self.enable_nurbs = enable_nurbs

    def convert(self, filepath: str) -> ConversionResult:
        """
        Konvertiert Mesh-Datei zu BREP Solid.

        Args:
            filepath: Pfad zur STL/OBJ/PLY Datei

        Returns:
            ConversionResult mit Status und Solid
        """
        logger.info(f"=== MeshToBREP V10 Converter ===")
        logger.info(f"Input: {filepath}")

        # 1. Mesh laden
        load_result = MeshLoader.load(filepath, repair=True)

        if load_result.status == LoadStatus.FAILED:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message=f"Laden fehlgeschlagen: {load_result.message}"
            )

        mesh = load_result.mesh
        logger.info(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        # 2. Konvertieren
        return self.convert_mesh(mesh)

    def convert_mesh(self, mesh: 'pv.PolyData') -> ConversionResult:
        """
        Konvertiert PyVista Mesh zu BREP Solid.

        Args:
            mesh: PyVista PolyData Objekt

        Returns:
            ConversionResult mit Status und Solid
        """
        if not HAS_BUILD123D:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="build123d nicht installiert"
            )

        stats = {
            'input_points': mesh.n_points,
            'input_faces': mesh.n_cells
        }

        try:
            # Import der Sub-Module (lazy loading)
            from meshconverter.surface_segmenter import SurfaceSegmenter
            from meshconverter.primitive_fitter import PrimitiveFitter
            from meshconverter.brep_face_factory import BRepFaceFactory
            from meshconverter.solid_builder import SolidBuilder

            # 1. Segmentierung
            logger.info("Segmentiere Oberflächen...")
            segmenter = SurfaceSegmenter(
                angle_tolerance=self.angle_tol,
                min_region_faces=self.min_region_faces
            )
            regions = segmenter.segment(mesh)
            stats['regions_detected'] = len(regions)
            logger.info(f"  → {len(regions)} Regionen erkannt")

            if len(regions) == 0:
                return ConversionResult(
                    status=ConversionStatus.FAILED,
                    message="Keine Regionen erkannt - Mesh möglicherweise zu chaotisch",
                    stats=stats
                )

            # 2. Primitive Fitting
            logger.info("Fitte Primitive...")
            fitter = PrimitiveFitter(
                tolerance=self.fitting_tol,
                enable_nurbs=self.enable_nurbs
            )
            primitives = []
            for region in regions:
                primitive = fitter.fit_region(mesh, region)
                if primitive:
                    primitives.append(primitive)
                    logger.debug(f"  Region {region.region_id}: {primitive.type} "
                               f"(confidence={primitive.confidence:.2f})")

            stats['primitives_detected'] = len(primitives)
            stats['coverage'] = len(primitives) / len(regions) if regions else 0
            logger.info(f"  → {len(primitives)}/{len(regions)} Primitive erkannt "
                       f"({stats['coverage']*100:.1f}% Coverage)")

            if len(primitives) == 0:
                return ConversionResult(
                    status=ConversionStatus.FAILED,
                    message="Keine Primitive erkannt",
                    stats=stats
                )

            # 3. BREP Faces erstellen
            logger.info("Erstelle BREP Faces...")
            factory = BRepFaceFactory()
            faces = []
            for prim in primitives:
                face = factory.create_face(prim)
                if face is not None:
                    faces.append(face)

            stats['faces_created'] = len(faces)
            logger.info(f"  → {len(faces)} Faces erstellt")

            if len(faces) == 0:
                return ConversionResult(
                    status=ConversionStatus.FAILED,
                    message="Keine BREP Faces erstellt",
                    stats=stats
                )

            # 4. Solid erstellen mit Multi-Pass Sewing
            logger.info("Erstelle Solid...")
            builder = SolidBuilder(
                tolerance=self.sewing_tol,
                multi_pass_sewing=True,
                max_tolerance=self.max_sewing_tol
            )
            result = builder.build(faces)

            # Stats ergänzen
            result.stats.update(stats)

            logger.info(f"=== Ergebnis: {result.status.name} ===")
            if result.message:
                logger.info(f"  Nachricht: {result.message}")

            return result

        except ImportError as e:
            logger.error(f"Import-Fehler: {e}")
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message=f"Modul nicht gefunden: {e}",
                stats=stats
            )
        except Exception as e:
            logger.error(f"Konvertierung fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message=f"Unerwarteter Fehler: {e}",
                stats=stats
            )


# =============================================================================
# Convenience Functions
# =============================================================================

def convert_stl_to_brep(
    filepath: str,
    mode: str = "auto",
    **kwargs
) -> ConversionResult:
    """
    Convenience-Funktion für STL-zu-BREP Konvertierung.

    Args:
        filepath: Pfad zur STL-Datei
        mode: Konvertierungsmodus
            - "auto": Versucht segmented, fällt auf direct zurück (Standard)
            - "direct": Direct Mesh Converter (100% Erfolgsrate, aber viele Faces)
            - "segmented": Segmentierungs-basiert (Primitive-Erkennung)
            - "topology": Topology-Preserving mit Segmentierung
        **kwargs: Optionen für den jeweiligen Konverter

    Returns:
        ConversionResult
    """
    if mode == "auto":
        # Hybrid-Ansatz: Versuche segmented, fallback auf direct
        logger.info("Auto-Modus: Versuche segmented Konvertierung...")
        converter = MeshToBREPConverterV10(**kwargs)
        result = converter.convert(filepath)

        if result.status == ConversionStatus.SUCCESS:
            logger.info("Segmented Konvertierung erfolgreich!")
            return result

        # Fallback auf DirectMeshConverter
        logger.warning(f"Segmented fehlgeschlagen ({result.message}), verwende DirectMeshConverter...")
        from meshconverter.direct_mesh_converter import convert_direct_mesh
        return convert_direct_mesh(filepath)

    elif mode == "direct":
        from meshconverter.direct_mesh_converter import convert_direct_mesh
        return convert_direct_mesh(filepath, **kwargs)
    elif mode == "topology":
        from meshconverter.topology_preserver import convert_topology_preserving
        return convert_topology_preserving(filepath, **kwargs)
    else:  # "segmented"
        converter = MeshToBREPConverterV10(**kwargs)
        return converter.convert(filepath)


def load_and_repair_mesh(filepath: str) -> LoadResult:
    """
    Lädt und repariert Mesh-Datei.

    Args:
        filepath: Pfad zur Mesh-Datei

    Returns:
        LoadResult mit repariertem Mesh
    """
    return MeshLoader.load(filepath, repair=True)


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python mesh_converter_v10.py <file.stl>")
        sys.exit(1)

    filepath = sys.argv[1]

    # Test Laden
    print("\n=== Test: Mesh Laden ===")
    load_result = MeshLoader.load(filepath)
    print(f"Status: {load_result.status.name}")
    print(f"Stats: {load_result.stats}")
    if load_result.repairs:
        print(f"Repairs: {load_result.repairs}")

    # Test Konvertierung (wenn alle Module vorhanden)
    print("\n=== Test: Konvertierung ===")
    try:
        result = convert_stl_to_brep(filepath)
        print(f"Status: {result.status.name}")
        print(f"Message: {result.message}")
        print(f"Stats: {result.stats}")

        if result.solid:
            print(f"Solid Type: {type(result.solid).__name__}")
    except Exception as e:
        print(f"Konvertierung noch nicht vollständig implementiert: {e}")
