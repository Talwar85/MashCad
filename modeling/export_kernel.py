"""
MashCAD - Export Kernel API
============================

Unified Export API für STL, STEP und 3MF Export.

Phase 1: Export Foundation (PR-001)
Zentrale Export-Schicht die GUI und Kernel vereinheitlicht.

Usage:
    from modeling.export_kernel import ExportKernel, ExportOptions, ExportFormat
    
    options = ExportOptions(
        format=ExportFormat.STL,
        linear_deflection=0.1,
        angular_tolerance=0.5,
        binary=True
    )
    
    result = ExportKernel.export_bodies(bodies, "/path/to/file.stl", options)
    if not result.success:
        print(f"Export failed: {result.error_message}")

Author: Kimi (Phase 1 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import List, Optional, Any, Dict, Union, Callable
from loguru import logger
import numpy as np


class ExportFormat(Enum):
    """Unterstützte Export-Formate."""
    STL = "stl"
    STEP = "step"
    STEP_AP214 = "step_ap214"
    STEP_AP242 = "step_ap242"
    _3MF = "3mf"
    OBJ = "obj"
    PLY = "ply"


class ExportQuality(Enum):
    """Export-Qualitäts-Presets."""
    DRAFT = (0.1, 0.5, "Draft")       # Schnell, grob
    STANDARD = (0.05, 0.3, "Standard") # Balance
    FINE = (0.01, 0.2, "Fine")        # Hochwertig
    ULTRA = (0.005, 0.1, "Ultra")     # Maximale Qualität
    
    def __init__(self, linear_deflection: float, angular_tolerance: float, label: str):
        self.linear_deflection = linear_deflection
        self.angular_tolerance = angular_tolerance
        self.label = label


@dataclass
class ExportOptions:
    """
    Export-Optionen für alle Formate.
    
    Args:
        format: Zielformat (STL, STEP, etc.)
        quality: Qualitäts-Preset (DRAFT, STANDARD, FINE, ULTRA)
        linear_deflection: Maximale Abweichung von der Kurve (mm)
        angular_tolerance: Winkel-Toleranz für Tessellation (rad)
        binary: True für Binärformat (STL), False für ASCII
        scale: Skalierungsfaktor (1.0 = mm, 1/25.4 = inch)
        author: Autor für STEP Metadata
        organization: Organisation für STEP Metadata
        schema: STEP Schema (AP214, AP242)
        metadata: Zusätzliche Metadaten für Export
    """
    format: ExportFormat = ExportFormat.STL
    quality: Optional[ExportQuality] = ExportQuality.FINE
    linear_deflection: float = 0.01
    angular_tolerance: float = 0.2
    binary: bool = True
    scale: float = 1.0
    author: str = ""
    organization: str = ""
    schema: str = "AP214"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Wende Quality-Preset an wenn gesetzt."""
        if self.quality is not None:
            self.linear_deflection = self.quality.linear_deflection
            self.angular_tolerance = self.quality.angular_tolerance


@dataclass
class ExportResult:
    """
    Ergebnis eines Export-Vorgangs.
    
    Args:
        success: True wenn Export erfolgreich
        filepath: Pfad zur exportierten Datei
        format: Verwendetes Format
        file_size_bytes: Dateigröße in Bytes
        triangle_count: Anzahl der Dreiecke (Mesh-Formate)
        body_count: Anzahl der exportierten Bodies
        warnings: Liste von Warnungen (nicht-kritisch)
        error_code: Fehler-Code bei Misserfolg
        error_message: Fehler-Beschreibung bei Misserfolg
        metadata: Zusätzliche Export-Metadaten
    """
    success: bool
    filepath: str = ""
    format: Optional[ExportFormat] = None
    file_size_bytes: int = 0
    triangle_count: int = 0
    body_count: int = 0
    warnings: List[str] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def file_size_kb(self) -> float:
        """Dateigröße in KB."""
        return self.file_size_bytes / 1024.0
    
    def add_warning(self, message: str):
        """Fügt eine Warnung hinzu."""
        self.warnings.append(message)
        logger.warning(f"Export warning: {message}")


@dataclass
class ExportCandidate:
    """
    Ein Kandidat für den Export (Body oder Solid).
    
    Args:
        body: Das Body-Objekt (optional)
        solid: Das Solid-Objekt (optional)
        name: Name für Export-Metadaten
        visible: Sichtbarkeit
        id: Eindeutige ID
    """
    body: Optional[Any] = None
    solid: Optional[Any] = None
    name: str = ""
    visible: bool = True
    id: str = ""
    
    def get_solid(self) -> Optional[Any]:
        """Extrahiert das Solid aus Body oder direkt."""
        if self.solid is not None:
            return self.solid
        if self.body is not None:
            return getattr(self.body, '_build123d_solid', None)
        return None
    
    def get_mesh(self) -> Optional[Any]:
        """Extrahiert das Mesh aus Body wenn verfügbar."""
        if self.body is not None:
            return getattr(self.body, '_mesh', None)
        return None


class ExportKernel:
    """
    Unified Export Kernel für alle Export-Operationen.
    
    Diese Klasse kapselt alle Export-Logik und bietet eine
    einheitliche API für GUI und andere Consumer.
    
    Usage:
        # Einfacher Export
        result = ExportKernel.export_bodies(bodies, "part.stl")
        
        # Mit Optionen
        options = ExportOptions(format=ExportFormat.STEP, quality=ExportQuality.FINE)
        result = ExportKernel.export_bodies(bodies, "part.step", options)
        
        # Mit Validierung
        result = ExportKernel.export_with_validation(bodies, "part.stl", options)
    """
    
    # Registry für Format-spezifische Exporter
    _exporters: Dict[ExportFormat, Callable] = {}
    
    @classmethod
    def register_exporter(cls, format: ExportFormat, exporter: Callable):
        """Registriert einen Exporter für ein Format."""
        cls._exporters[format] = exporter
        logger.debug(f"Registered exporter for {format.value}")
    
    @staticmethod
    def export_bodies(
        bodies: List[Any],
        filepath: Union[str, Path],
        options: Optional[ExportOptions] = None
    ) -> ExportResult:
        """
        Exportiert eine Liste von Bodies.
        
        Args:
            bodies: Liste von Body-Objekten
            filepath: Zielpfad für die Export-Datei
            options: Export-Optionen (oder Default)
            
        Returns:
            ExportResult mit Erfolgsstatus und Metadaten
        """
        if options is None:
            options = ExportOptions()
        
        filepath = Path(filepath)
        
        # Format aus Extension ableiten falls nicht explizit gesetzt
        if options.format is None:
            options.format = ExportKernel._detect_format_from_extension(filepath)
        
        logger.info(f"Exporting {len(bodies)} bodies to {filepath} ({options.format.value})")
        
        # Filtere gültige Kandidaten
        candidates = ExportKernel._prepare_candidates(bodies)
        if not candidates:
            return ExportResult(
                success=False,
                error_code="NO_VALID_BODIES",
                error_message="Keine gültigen Bodies zum Exportieren gefunden."
            )
        
        # Route zum Format-spezifischen Exporter
        try:
            if options.format == ExportFormat.STL:
                return ExportKernel._export_stl(candidates, filepath, options)
            elif options.format in (ExportFormat.STEP, ExportFormat.STEP_AP214, ExportFormat.STEP_AP242):
                return ExportKernel._export_step(candidates, filepath, options)
            elif options.format == ExportFormat._3MF:
                return ExportKernel._export_3mf(candidates, filepath, options)
            elif options.format == ExportFormat.OBJ:
                return ExportKernel._export_obj(candidates, filepath, options)
            elif options.format == ExportFormat.PLY:
                return ExportKernel._export_ply(candidates, filepath, options)
            else:
                return ExportResult(
                    success=False,
                    error_code="UNSUPPORTED_FORMAT",
                    error_message=f"Format {options.format.value} wird nicht unterstützt."
                )
        except Exception as e:
            logger.exception(f"Export failed: {e}")
            return ExportResult(
                success=False,
                error_code="EXPORT_EXCEPTION",
                error_message=str(e)
            )
    
    @staticmethod
    def export_with_validation(
        bodies: List[Any],
        filepath: Union[str, Path],
        options: Optional[ExportOptions] = None,
        validation_options: Optional[Dict] = None
    ) -> ExportResult:
        """
        Exportiert mit Pre-flight Validierung.
        
        Args:
            bodies: Zu exportierende Bodies
            filepath: Zielpfad
            options: Export-Optionen
            validation_options: Optionen für die Validierung
            
        Returns:
            ExportResult (kann Warnungen enthalten)
        """
        from modeling.export_validator import ExportValidator, ValidationSeverity
        
        # Validierung durchführen
        candidates = ExportKernel._prepare_candidates(bodies)
        validation_results = []
        
        for candidate in candidates:
            solid = candidate.get_solid()
            if solid is not None:
                result = ExportValidator.validate_for_export(solid)
                validation_results.append(result)
        
        # Kritische Fehler prüfen
        critical_issues = []
        for result in validation_results:
            for issue in result.issues:
                if issue.severity == ValidationSeverity.ERROR:
                    critical_issues.append(issue.message)
        
        if critical_issues and (validation_options or {}).get('block_on_error', True):
            return ExportResult(
                success=False,
                error_code="VALIDATION_FAILED",
                error_message=f"Export blockiert: {'; '.join(critical_issues[:3])}"
            )
        
        # Export durchführen
        export_result = ExportKernel.export_bodies(bodies, filepath, options)
        
        # Warnungen hinzufügen
        for result in validation_results:
            for issue in result.issues:
                if issue.severity == ValidationSeverity.WARNING:
                    export_result.add_warning(issue.message)
        
        return export_result
    
    @staticmethod
    def _prepare_candidates(bodies: List[Any]) -> List[ExportCandidate]:
        """Bereitet Export-Kandidaten vor."""
        candidates = []
        
        for body in bodies:
            if body is None:
                continue
                
            # Prüfe auf sichtbar
            visible = getattr(body, 'visible', True)
            if not visible:
                continue
            
            candidate = ExportCandidate(
                body=body,
                name=getattr(body, 'name', ''),
                id=getattr(body, 'id', ''),
                visible=visible
            )
            candidates.append(candidate)
        
        return candidates
    
    @staticmethod
    def _detect_format_from_extension(filepath: Path) -> ExportFormat:
        """Erkennt Format aus Datei-Erweiterung."""
        ext = filepath.suffix.lower()
        
        mapping = {
            '.stl': ExportFormat.STL,
            '.step': ExportFormat.STEP,
            '.stp': ExportFormat.STEP,
            '.3mf': ExportFormat._3MF,
            '.obj': ExportFormat.OBJ,
            '.ply': ExportFormat.PLY,
        }
        
        return mapping.get(ext, ExportFormat.STL)
    
    @staticmethod
    def _export_stl(
        candidates: List[ExportCandidate],
        filepath: Path,
        options: ExportOptions
    ) -> ExportResult:
        """STL Export Implementierung."""
        try:
            import pyvista as pv
            from modeling.cad_tessellator import CADTessellator
            
            merged_polydata = None
            total_triangles = 0
            
            for candidate in candidates:
                mesh_to_add = None
                solid = candidate.get_solid()
                
                if solid is not None:
                    # Tessellate mit CADTessellator
                    try:
                        verts, faces_tris = CADTessellator.tessellate_for_export(
                            solid,
                            linear_deflection=options.linear_deflection,
                            angular_tolerance=options.angular_tolerance
                        )
                        if verts and faces_tris:
                            faces = []
                            for t in faces_tris:
                                faces.extend([3] + list(t))
                            mesh_to_add = pv.PolyData(np.array(verts), np.array(faces))
                    except Exception as e:
                        logger.warning(f"Tessellation failed for {candidate.name}: {e}")
                
                # Fallback auf existierendes Mesh
                if mesh_to_add is None:
                    mesh = candidate.get_mesh()
                    if mesh is not None and hasattr(mesh, 'points'):
                        mesh_to_add = mesh
                
                if mesh_to_add:
                    if merged_polydata is None:
                        merged_polydata = mesh_to_add
                    else:
                        merged_polydata = merged_polydata.merge(mesh_to_add)
                    total_triangles += mesh_to_add.n_cells
            
            if merged_polydata is None:
                return ExportResult(
                    success=False,
                    error_code="NO_MESH_DATA",
                    error_message="Keine Mesh-Daten zum Exportieren generiert."
                )
            
            # Skalierung anwenden
            if abs(options.scale - 1.0) > 1e-6:
                merged_polydata.points *= options.scale
            
            # Speichern
            filepath.parent.mkdir(parents=True, exist_ok=True)
            merged_polydata.save(str(filepath), binary=options.binary)
            
            file_size = filepath.stat().st_size if filepath.exists() else 0
            
            return ExportResult(
                success=True,
                filepath=str(filepath),
                format=ExportFormat.STL,
                file_size_bytes=file_size,
                triangle_count=total_triangles,
                body_count=len(candidates)
            )
            
        except ImportError as e:
            return ExportResult(
                success=False,
                error_code="MISSING_DEPENDENCY",
                error_message=f"Fehlende Abhängigkeit: {e}"
            )
        except Exception as e:
            return ExportResult(
                success=False,
                error_code="STL_EXPORT_ERROR",
                error_message=str(e)
            )
    
    @staticmethod
    def _export_step(
        candidates: List[ExportCandidate],
        filepath: Path,
        options: ExportOptions
    ) -> ExportResult:
        """STEP Export Implementierung."""
        try:
            from modeling.step_io import STEPWriter, STEPSchema
            
            # Sammle alle Solids
            solids = []
            for candidate in candidates:
                solid = candidate.get_solid()
                if solid is not None:
                    solids.append(solid)
            
            if not solids:
                return ExportResult(
                    success=False,
                    error_code="NO_VALID_SOLIDS",
                    error_message="Keine gültigen Solids für STEP-Export gefunden."
                )
            
            # Schema wählen
            schema = STEPSchema.AP214
            if options.schema == "AP242" or options.format == ExportFormat.STEP_AP242:
                schema = STEPSchema.AP242
            
            # Export durchführen
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            if len(solids) == 1:
                result = STEPWriter.export_solid(
                    solids[0],
                    str(filepath),
                    schema=schema,
                    author=options.author,
                    organization=options.organization
                )
            else:
                result = STEPWriter.export_assembly(
                    solids,
                    str(filepath),
                    schema=schema
                )
            
            return ExportResult(
                success=result.success,
                filepath=str(filepath),
                format=ExportFormat.STEP,
                file_size_bytes=result.file_size_bytes,
                body_count=len(solids),
                error_message=result.message if not result.success else ""
            )
            
        except ImportError as e:
            return ExportResult(
                success=False,
                error_code="MISSING_DEPENDENCY",
                error_message=f"Fehlende Abhängigkeit: {e}"
            )
        except Exception as e:
            return ExportResult(
                success=False,
                error_code="STEP_EXPORT_ERROR",
                error_message=str(e)
            )
    
    @staticmethod
    def _export_3mf(
        candidates: List[ExportCandidate],
        filepath: Path,
        options: ExportOptions
    ) -> ExportResult:
        """3MF Export Implementierung (Placeholder)."""
        # TODO: Implement 3MF Export
        return ExportResult(
            success=False,
            error_code="NOT_IMPLEMENTED",
            error_message="3MF Export ist noch nicht implementiert."
        )
    
    @staticmethod
    def _export_obj(
        candidates: List[ExportCandidate],
        filepath: Path,
        options: ExportOptions
    ) -> ExportResult:
        """OBJ Export Implementierung."""
        try:
            # STL als Basis, dann meshio für OBJ Konvertierung
            stl_result = ExportKernel._export_stl(candidates, filepath.with_suffix('.tmp.stl'), options)
            if not stl_result.success:
                return stl_result
            
            import meshio
            mesh = meshio.read(str(filepath.with_suffix('.tmp.stl')))
            mesh.write(str(filepath), file_format='obj')
            
            # Cleanup temp file
            filepath.with_suffix('.tmp.stl').unlink(missing_ok=True)
            
            file_size = filepath.stat().st_size if filepath.exists() else 0
            
            return ExportResult(
                success=True,
                filepath=str(filepath),
                format=ExportFormat.OBJ,
                file_size_bytes=file_size,
                triangle_count=stl_result.triangle_count,
                body_count=stl_result.body_count
            )
            
        except ImportError:
            return ExportResult(
                success=False,
                error_code="MISSING_DEPENDENCY",
                error_message="meshio wird für OBJ Export benötigt."
            )
        except Exception as e:
            return ExportResult(
                success=False,
                error_code="OBJ_EXPORT_ERROR",
                error_message=str(e)
            )
    
    @staticmethod
    def _export_ply(
        candidates: List[ExportCandidate],
        filepath: Path,
        options: ExportOptions
    ) -> ExportResult:
        """PLY Export Implementierung."""
        try:
            # STL als Basis, dann meshio für PLY Konvertierung
            stl_result = ExportKernel._export_stl(candidates, filepath.with_suffix('.tmp.stl'), options)
            if not stl_result.success:
                return stl_result
            
            import meshio
            mesh = meshio.read(str(filepath.with_suffix('.tmp.stl')))
            mesh.write(str(filepath), file_format='ply')
            
            # Cleanup temp file
            filepath.with_suffix('.tmp.stl').unlink(missing_ok=True)
            
            file_size = filepath.stat().st_size if filepath.exists() else 0
            
            return ExportResult(
                success=True,
                filepath=str(filepath),
                format=ExportFormat.PLY,
                file_size_bytes=file_size,
                triangle_count=stl_result.triangle_count,
                body_count=stl_result.body_count
            )
            
        except ImportError:
            return ExportResult(
                success=False,
                error_code="MISSING_DEPENDENCY",
                error_message="meshio wird für PLY Export benötigt."
            )
        except Exception as e:
            return ExportResult(
                success=False,
                error_code="PLY_EXPORT_ERROR",
                error_message=str(e)
            )
    
    @staticmethod
    def estimate_triangle_count(
        bodies: List[Any],
        linear_deflection: float = 0.01
    ) -> int:
        """
        Schätzt die Anzahl der Dreiecke für STL Export.
        
        Args:
            bodies: Liste von Bodies
            linear_deflection: Geplante Tessellation-Qualität
            
        Returns:
            Geschätzte Anzahl der Dreiecke
        """
        total_estimate = 0
        
        for body in bodies:
            solid = getattr(body, '_build123d_solid', None)
            if solid is None:
                continue
            
            # Einfache Heuristik basierend auf Bounding Box und Qualität
            try:
                if hasattr(solid, 'bounding_box'):
                    bbox = solid.bounding_box
                    volume = abs(bbox.max - bbox.min).length
                    # Heuristik: ~100 Dreiecke pro mm³ bei 0.1 Deflection
                    scale_factor = 0.1 / max(linear_deflection, 0.001)
                    estimate = int(volume * 100 * scale_factor)
                    total_estimate += max(estimate, 10)  # Minimum 10 Dreiecke
            except Exception:
                pass
        
        return total_estimate
    
    @staticmethod
    def get_supported_formats() -> List[Dict[str, str]]:
        """
        Gibt Liste der unterstützten Formate zurück.
        
        Returns:
            Liste von Dicts mit 'format', 'extension', 'description'
        """
        return [
            {"format": "STL", "extension": ".stl", "description": "Standard Tessellation Language"},
            {"format": "STEP", "extension": ".step", "description": "ISO 10303 (AP214/AP242)"},
            {"format": "STEP", "extension": ".stp", "description": "ISO 10303 (kurze Extension)"},
            {"format": "3MF", "extension": ".3mf", "description": "3D Manufacturing Format (geplant)"},
            {"format": "OBJ", "extension": ".obj", "description": "Wavefront OBJ"},
            {"format": "PLY", "extension": ".ply", "description": "Polygon File Format"},
        ]


# =============================================================================
# Convenience Functions
# =============================================================================

def export_stl(bodies: List[Any], filepath: str, **kwargs) -> ExportResult:
    """Shortcut für STL Export."""
    options = ExportOptions(format=ExportFormat.STL, **kwargs)
    return ExportKernel.export_bodies(bodies, filepath, options)


def export_step(bodies: List[Any], filepath: str, **kwargs) -> ExportResult:
    """Shortcut für STEP Export."""
    options = ExportOptions(format=ExportFormat.STEP, **kwargs)
    return ExportKernel.export_bodies(bodies, filepath, options)


def quick_export(bodies: List[Any], filepath: str) -> bool:
    """
    Schneller Export ohne Optionen.
    
    Args:
        bodies: Zu exportierende Bodies
        filepath: Zielpfad (Format aus Extension erkannt)
        
    Returns:
        True bei Erfolg, False bei Fehler
    """
    result = ExportKernel.export_bodies(bodies, filepath)
    return result.success
