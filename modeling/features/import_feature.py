
from dataclasses import dataclass, field
from .base import Feature, FeatureType

@dataclass
class ImportFeature(Feature):
    """
    Import Feature - Speichert die Original-BREP eines importierten Bodies.

    Wird verwendet für:
    - Mesh-zu-CAD Konvertierung (STL/OBJ → BREP)
    - STEP/IGES Import
    - Jede externe Geometrie die als Basis für weitere Features dient

    Die BREP wird als String gespeichert (via BRepTools.Write_s) um Serialisierung
    zu ermöglichen. Beim Rebuild wird die BREP aus dem String rekonstruiert.
    """
    brep_string: str = ""  # BREP als String (via BRepTools.Write_s)
    source_file: str = ""  # Original-Dateiname (für Anzeige)
    source_type: str = ""  # "mesh_convert", "step_import", "iges_import"

    def __post_init__(self):
        self.type = FeatureType.IMPORT
        if not self.name or self.name == "Feature":
            if self.source_file:
                self.name = f"Import ({self.source_file})"
            else:
                self.name = "Import"

    def get_solid(self):
        """Rekonstruiert das Solid aus dem BREP-String."""
        if not self.brep_string:
            return None
        try:
            from OCP.BRepTools import BRepTools
            from OCP.TopoDS import TopoDS_Shape
            from OCP.BRep import BRep_Builder
            from build123d import Solid
            import io

            builder = BRep_Builder()
            shape = TopoDS_Shape()

            # BREP aus String lesen (via BytesIO Stream)
            stream = io.BytesIO(self.brep_string.encode('utf-8'))
            BRepTools.Read_s(shape, stream, builder)

            if not shape.IsNull():
                return Solid(shape)
        except Exception as e:
            from loguru import logger
            logger.error(f"ImportFeature.get_solid() fehlgeschlagen: {e}")
        return None
