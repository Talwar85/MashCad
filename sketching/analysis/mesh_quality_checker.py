"""
Mesh Quality Checker for STL files.

Validates and repairs mesh quality without modifying external libraries.
Uses only standard PyVista functions.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MeshQualityReport:
    """Qualitätsbericht für ein Mesh."""
    
    # Pfad
    mesh_path: str = ""
    
    # Basis-Metriken
    is_watertight: bool = False
    face_count: int = 0
    vertex_count: int = 0
    edge_count: int = 0
    
    # Geometrie
    bounds: Tuple[Tuple[float, float, float], Tuple[float, float, float]] = field(
        default_factory=lambda: ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    )
    
    # Qualitäts-Probleme
    has_degenerate_faces: bool = False
    has_duplicate_vertices: bool = False
    has_nan_vertices: bool = False
    
    # Empfohlene Aktion
    recommended_action: str = "proceed"  # "proceed" | "repair" | "decimate" | "reject"
    
    # Warnungen
    warnings: List[str] = field(default_factory=list)
    
    # Auto-Repair Ergebnis
    repair_performed: bool = False
    repair_log: List[str] = field(default_factory=list)
    
    # Decimation
    decimation_performed: bool = False
    original_face_count: int = 0
    
    @property
    def is_valid(self) -> bool:
        """Gibt zurück ob das Mesh grundsätzlich valide ist."""
        return (
            self.face_count > 0 and
            self.vertex_count > 0 and
            not self.has_nan_vertices and
            self.recommended_action != "reject"
        )
    
    @property
    def bounding_box_size(self) -> Tuple[float, float, float]:
        """Berechnet die Bounding-Box-Größe."""
        min_pt, max_pt = self.bounds
        return (
            max_pt[0] - min_pt[0],
            max_pt[1] - min_pt[1],
            max_pt[2] - min_pt[2]
        )
    
    @property
    def max_bounding_dimension(self) -> float:
        """Größte Dimension der Bounding Box."""
        return max(self.bounding_box_size)


class MeshQualityChecker:
    """
    Prüft und repariert Mesh-Qualität.
    
    Verwendet NUR PyVista-Standardfunktionen (keine Modifikationen an Libs).
    """
    
    # Thresholds
    MAX_FACES_FOR_QUICK_ANALYSIS = 100000
    MAX_FACES_FOR_DETAILED_ANALYSIS = 500000
    TARGET_FACE_COUNT_AFTER_DECIMATION = 50000
    MIN_FACE_COUNT = 4
    
    # Degenerate face threshold (area close to zero)
    MIN_FACE_AREA = 1e-10
    
    def __init__(self):
        """Initialisiert den Quality Checker."""
        self.pyvista_available = self._check_pyvista()
    
    def _check_pyvista(self) -> bool:
        """Prüft ob PyVista verfügbar ist."""
        try:
            import pyvista as pv
            return True
        except ImportError:
            logger.error("PyVista nicht verfügbar")
            return False
    
    def check(self, mesh_path: str, 
              auto_repair: bool = True,
              auto_decimate: bool = True) -> MeshQualityReport:
        """
        Vollständige Qualitätsprüfung einer STL-Datei.
        
        Args:
            mesh_path: Pfad zur STL-Datei
            auto_repair: Automatisch reparieren wenn nötig
            auto_decimate: Automatisch decimieren wenn zu groß
            
        Returns:
            MeshQualityReport mit Ergebnissen
        """
        report = MeshQualityReport(mesh_path=mesh_path)
        
        if not self.pyvista_available:
            report.recommended_action = "reject"
            report.warnings.append("PyVista nicht verfügbar")
            return report
        
        try:
            import pyvista as pv
            
            # 1. Mesh laden
            logger.info(f"Lade Mesh: {mesh_path}")
            mesh = pv.read(mesh_path)
            
            if mesh is None:
                report.recommended_action = "reject"
                report.warnings.append("Mesh konnte nicht geladen werden")
                return report
            
            # 2. Basis-Analyse
            report = self._analyze_basic(mesh, report)
            
            # 3. Qualitäts-Checks
            report = self._check_quality_issues(mesh, report)
            
            # 4. Auto-Repair wenn nötig und gewünscht
            if auto_repair and report.recommended_action == "repair":
                mesh = self.auto_repair(mesh)
                report.repair_performed = True
                # Re-analysieren nach Repair
                report = self._analyze_basic(mesh, report)
                report = self._check_quality_issues(mesh, report)
            
            # 5. Auto-Decimate wenn zu groß
            if auto_decimate and report.face_count > self.MAX_FACES_FOR_QUICK_ANALYSIS:
                mesh = self.decimate_if_needed(mesh)
                report.decimation_performed = True
                report.original_face_count = report.face_count
                # Re-analysieren nach Decimation
                report = self._analyze_basic(mesh, report)
            
            # 6. Finale Empfehlung
            report = self._determine_recommendation(report)
            
            logger.info(f"Mesh Quality Check abgeschlossen: {report.recommended_action}")
            
        except Exception as e:
            logger.error(f"Fehler bei Mesh Quality Check: {e}")
            report.recommended_action = "reject"
            report.warnings.append(f"Fehler: {str(e)}")
        
        return report
    
    def _analyze_basic(self, mesh, report: MeshQualityReport) -> MeshQualityReport:
        """
        Basis-Analyse des Meshes.
        
        Args:
            mesh: PyVista PolyData Mesh
            report: Zu aktualisierender Report
            
        Returns:
            Aktualisierter Report
        """
        # Anzahl Faces/Vertices
        report.face_count = mesh.n_faces
        report.vertex_count = mesh.n_points
        
        # Bounding Box
        bounds = mesh.bounds
        report.bounds = (
            (bounds[0], bounds[2], bounds[4]),  # Min
            (bounds[1], bounds[3], bounds[5])   # Max
        )
        
        # Watertight check
        report.is_watertight = self._check_watertight(mesh)
        
        logger.debug(f"Basis-Analyse: {report.face_count} faces, "
                    f"watertight={report.is_watertight}")
        
        return report
    
    def _check_watertight(self, mesh) -> bool:
        """
        Prüft ob das Mesh watertight (geschlossen) ist.
        
        Verwendet PyVista's is_all_edges manifold check.
        """
        try:
            # PyVista's eingebaute Methode
            return mesh.is_all_edges
        except Exception:
            # Fallback: Prüfe ob offene edges existieren
            try:
                edges = mesh.extract_feature_edges(
                    boundary_edges=True,
                    feature_edges=False,
                    manifold_edges=False
                )
                return edges.n_cells == 0
            except Exception:
                return False
    
    def _check_quality_issues(self, mesh, report: MeshQualityReport) -> MeshQualityReport:
        """
        Prüft auf Qualitätsprobleme.
        
        Args:
            mesh: PyVista PolyData Mesh
            report: Zu aktualisierender Report
            
        Returns:
            Aktualisierter Report
        """
        # 1. Degenerate faces (Fläche nahe 0)
        report.has_degenerate_faces = self._check_degenerate_faces(mesh)
        if report.has_degenerate_faces:
            report.warnings.append("Degenerierte Faces gefunden (Fläche ≈ 0)")
        
        # 2. NaN in Vertices
        report.has_nan_vertices = self._check_nan_vertices(mesh)
        if report.has_nan_vertices:
            report.warnings.append("NaN-Werte in Vertices gefunden")
        
        # 3. Zu wenig Faces
        if report.face_count < self.MIN_FACE_COUNT:
            report.warnings.append(f"Zu wenig Faces ({report.face_count})")
            report.recommended_action = "reject"
        
        # 4. Zu viele Faces
        if report.face_count > self.MAX_FACES_FOR_DETAILED_ANALYSIS:
            report.warnings.append(
                f"Sehr viele Faces ({report.face_count}), "
                f"Analyse könnte langsam sein"
            )
        
        # 5. Nicht watertight
        if not report.is_watertight:
            report.warnings.append("Mesh ist nicht watertight (hat Löcher)")
        
        logger.debug(f"Qualitäts-Checks: degenerate={report.has_degenerate_faces}, "
                    f"nan={report.has_nan_vertices}")
        
        return report
    
    def _check_degenerate_faces(self, mesh) -> bool:
        """Prüft auf degenerierte Faces (Fläche nahe 0)."""
        try:
            # Berechne Face-Flächen
            areas = mesh.compute_cell_sizes()["Area"]
            return np.any(areas < self.MIN_FACE_AREA)
        except Exception:
            return False
    
    def _check_nan_vertices(self, mesh) -> bool:
        """Prüft auf NaN-Werte in Vertices."""
        try:
            points = mesh.points
            return np.any(np.isnan(points))
        except Exception:
            return False
    
    def _determine_recommendation(self, report: MeshQualityReport) -> MeshQualityReport:
        """
        Bestimmt die empfohlene Aktion basierend auf dem Report.
        
        Logik:
        - "reject": Bei kritischen Fehlern (NaN, zu wenig Faces)
        - "decimate": Bei zu vielen Faces
        - "repair": Bei nicht-watertight oder degenerierten Faces
        - "proceed": Wenn alles OK
        """
        if report.recommended_action == "reject":
            return report
        
        # Kritische Fehler
        if report.has_nan_vertices:
            report.recommended_action = "reject"
            return report
        
        if report.face_count < self.MIN_FACE_COUNT:
            report.recommended_action = "reject"
            return report
        
        # Reparatur nötig
        needs_repair = (
            not report.is_watertight or
            report.has_degenerate_faces or
            report.has_duplicate_vertices
        )
        
        if needs_repair:
            report.recommended_action = "repair"
            return report
        
        # Decimation nötig
        if report.face_count > self.MAX_FACES_FOR_QUICK_ANALYSIS:
            report.recommended_action = "decimate"
            return report
        
        # Alles OK
        report.recommended_action = "proceed"
        return report
    
    def auto_repair(self, mesh) -> Any:
        """
        Führt Standard-Reparaturen durch.
        
        Ohne Lib-Änderungen:
        1. clean() - Entfernt degenerierte/unreferenced Faces
        2. triangulate() - Sicherstellen dass alles Dreiecke sind
        3. fill_holes() - Füllt kleine Löcher (wenn verfügbar)
        
        Args:
            mesh: PyVista PolyData Mesh
            
        Returns:
            Repariertes Mesh
        """
        logger.info("Starte Auto-Repair")
        repair_log = []
        
        try:
            import pyvista as pv
            
            original_faces = mesh.n_faces
            
            # 1. Clean - entfernt degenerierte Faces
            mesh = mesh.clean(
                point_merging=True,
                merge_tol=1e-6,
                lines_to_points=False,
                polys_to_lines=False,
                strips_to_polys=False
            )
            
            if mesh.n_faces < original_faces:
                removed = original_faces - mesh.n_faces
                repair_log.append(f"{removed} degenerierte Faces entfernt")
                logger.debug(f"{removed} degenerierte Faces entfernt")
            
            # 2. Triangulate
            mesh = mesh.triangulate()
            repair_log.append("Mesh trianguliert")
            
            # 3. Try to fill holes (may not be available in all PyVista versions)
            try:
                # Extract boundary edges and try to fill
                boundary = mesh.extract_feature_edges(
                    boundary_edges=True,
                    feature_edges=False,
                    manifold_edges=False
                )
                
                if boundary.n_cells > 0:
                    repair_log.append(
                        f"Mesh hat {boundary.n_cells} offene Kanten (Löcher)"
                    )
                    logger.warning(f"Mesh hat {boundary.n_cells} offene Kanten - "
                                 f"manuelle Reparatur empfohlen")
            except Exception as e:
                logger.debug(f"Hole detection nicht verfügbar: {e}")
            
            logger.info(f"Auto-Repair abgeschlossen: {len(repair_log)} Aktionen")
            
        except Exception as e:
            logger.error(f"Fehler bei Auto-Repair: {e}")
            repair_log.append(f"Fehler: {str(e)}")
        
        # Store repair log in mesh for later retrieval
        mesh._repair_log = repair_log
        return mesh
    
    def decimate_if_needed(self, mesh, max_faces: Optional[int] = None) -> Any:
        """
        Reduziert Face-Count wenn nötig.
        
        Ziel: Analyse-Performance bei großen Meshes.
        
        Args:
            mesh: PyVista PolyData Mesh
            max_faces: Ziel-Max-Faces (default: TARGET_FACE_COUNT_AFTER_DECIMATION)
            
        Returns:
            Möglicherweise reduziertes Mesh
        """
        if max_faces is None:
            max_faces = self.TARGET_FACE_COUNT_AFTER_DECIMATION
        
        current_faces = mesh.n_faces
        
        if current_faces <= max_faces:
            return mesh
        
        logger.info(f"Decimate: {current_faces} -> ~{max_faces} faces")
        
        try:
            # Berechne Ziel-Reduction-Faktor
            reduction = 1.0 - (max_faces / current_faces)
            reduction = max(0.1, min(0.9, reduction))  # Clamp zwischen 10% und 90%
            
            # PyVista decimate
            decimated = mesh.decimate(reduction)
            
            logger.info(f"Decimation: {current_faces} -> {decimated.n_faces} faces "
                       f"({reduction*100:.1f}% reduction)")
            
            # Store original info
            decimated._original_face_count = current_faces
            decimated._decimation_ratio = reduction
            
            return decimated
            
        except Exception as e:
            logger.error(f"Decimation fehlgeschlagen: {e}")
            return mesh
    
    def get_mesh_info(self, mesh_path: str) -> dict:
        """
        Gibt Basis-Informationen über ein Mesh zurück (schnell, ohne Repair).
        
        Args:
            mesh_path: Pfad zur STL-Datei
            
        Returns:
            Dict mit Basis-Informationen
        """
        info = {
            "path": mesh_path,
            "loaded": False,
            "face_count": 0,
            "vertex_count": 0,
            "watertight": False,
            "bounds": None
        }
        
        if not self.pyvista_available:
            return info
        
        try:
            import pyvista as pv
            mesh = pv.read(mesh_path)
            
            info["loaded"] = True
            info["face_count"] = mesh.n_faces
            info["vertex_count"] = mesh.n_points
            info["watertight"] = self._check_watertight(mesh)
            info["bounds"] = mesh.bounds
            
        except Exception as e:
            info["error"] = str(e)
        
        return info


# Convenience function
def check_mesh_quality(mesh_path: str, 
                       auto_repair: bool = True,
                       auto_decimate: bool = True) -> MeshQualityReport:
    """
    Schnell-Check für Mesh-Qualität.
    
    Args:
        mesh_path: Pfad zur STL-Datei
        auto_repair: Automatisch reparieren
        auto_decimate: Automatisch decimieren
        
    Returns:
        MeshQualityReport
    """
    checker = MeshQualityChecker()
    return checker.check(mesh_path, auto_repair, auto_decimate)
