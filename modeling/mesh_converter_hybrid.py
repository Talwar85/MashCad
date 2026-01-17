"""
MashCad - Hybrid Mesh Converter (V9)
=====================================
Intelligenter Converter mit automatischer Methoden-Auswahl.

Strategie:
1. STUFE 1: RANSAC Primitive Detection (V7)
   - Schnell, keine ML-Dependency
   - Coverage-Check: > 80% → fertig

2. STUFE 2: Fallback zu V6 Smart Converter
   - Bei niedriger RANSAC-Coverage
   - Planare Regionen-Erkennung

3. STUFE 3: Fallback zu V1 Sewing
   - Wenn alles andere fehlschlägt
   - Immer verfügbar

Best-of-Both: Kombiniert Geschwindigkeit (RANSAC) mit Robustheit (Fallbacks)
"""

import numpy as np
from loguru import logger
from typing import Optional

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False
    logger.warning("PyVista nicht verfügbar")

try:
    from build123d import Solid, Shape
    HAS_BUILD123D = True
except ImportError:
    HAS_BUILD123D = False
    logger.warning("build123d nicht verfügbar")


class HybridMeshConverter:
    """
    Hybrid Mesh-zu-BREP Converter mit automatischer Methoden-Auswahl.

    Probiert nacheinander:
    1. V7 (RANSAC Primitives) - schnell, präzise
    2. V6 (Smart Planar) - robust für prismatische Teile
    3. V1 (Sewing) - immer verfügbar
    """

    def __init__(self,
                 ransac_min_coverage: float = 0.80,  # 80% Coverage für RANSAC-Erfolg
                 use_v7: bool = True,                # V7 aktiviert?
                 use_v6_fallback: bool = True,       # V6 als Fallback?
                 use_v1_fallback: bool = True):      # V1 als letzter Fallback?
        """
        Args:
            ransac_min_coverage: Minimum Coverage für RANSAC-Akzeptanz
            use_v7: RANSAC Primitives nutzen (V7)
            use_v6_fallback: Smart Planar als Fallback (V6)
            use_v1_fallback: Sewing als letzter Fallback (V1)
        """
        self.min_coverage = ransac_min_coverage
        self.use_v7 = use_v7
        self.use_v6_fallback = use_v6_fallback
        self.use_v1_fallback = use_v1_fallback

    def convert(self, mesh: 'pv.PolyData') -> Optional['Shape']:
        """
        Konvertiert PyVista Mesh zu Build123d Solid mit automatischer Methoden-Auswahl.

        Args:
            mesh: PyVista PolyData Objekt

        Returns:
            Build123d Solid oder None bei Fehler
        """
        if not HAS_PYVISTA or not HAS_BUILD123D:
            logger.error("Abhängigkeiten fehlen (PyVista, build123d)")
            return None

        logger.info("=== Hybrid Mesh Converter V9 ===")
        logger.info(f"Input: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        solid = None
        method_used = None

        # STUFE 1: RANSAC Primitive Detection (V7)
        if self.use_v7:
            logger.info("🔍 Stufe 1: RANSAC Primitive Detection (V7)...")
            try:
                from modeling.mesh_converter_primitives import RANSACPrimitiveConverter, HAS_RANSAC

                if not HAS_RANSAC:
                    logger.warning("⚠️ V7 übersprungen: pyransac3d nicht installiert")
                else:
                    converter_v7 = RANSACPrimitiveConverter(
                        angle_tolerance=5.0,
                        ransac_threshold=0.5,
                        min_inlier_ratio=0.70,
                        min_region_faces=10,
                        sewing_tolerance=0.1
                    )

                    # Versuche V7
                    solid, coverage = self._try_ransac(converter_v7, mesh)

                    if solid and coverage >= self.min_coverage:
                        logger.success(f"✅ RANSAC erfolgreich (Coverage: {coverage*100:.1f}%)")
                        method_used = "V7 (RANSAC Primitives)"
                        return solid
                    elif solid:
                        logger.info(f"⚠️ RANSAC niedrige Coverage ({coverage*100:.1f}%), "
                                  f"versuche Fallback...")
                    else:
                        logger.warning("⚠️ RANSAC fehlgeschlagen, versuche Fallback...")

            except ImportError as e:
                logger.warning(f"⚠️ V7 nicht verfügbar (Import-Fehler: {e})")
            except Exception as e:
                logger.warning(f"⚠️ V7 fehlgeschlagen: {e}")
                import traceback
                logger.debug(traceback.format_exc())

        # STUFE 2: Smart Planar Converter (V6)
        if self.use_v6_fallback and not solid:
            logger.info("🔍 Stufe 2: Smart Planar Converter (V6)...")
            try:
                from modeling.mesh_converter_v6 import SmartMeshConverter

                converter_v6 = SmartMeshConverter(
                    angle_tolerance=5.0,
                    min_region_faces=3,
                    decimate_target=5000,
                    sewing_tolerance=0.1
                )

                result = converter_v6.convert(mesh, method="smart")

                if result:
                    logger.success(f"✅ V6 Smart Converter erfolgreich (Typ: {type(result).__name__})")
                    method_used = "V6 (Smart Planar)"
                    return result
                else:
                    logger.warning("⚠️ V6 gab None zurück, versuche letzten Fallback...")

            except ImportError as e:
                logger.warning(f"⚠️ V6 nicht verfügbar: {e}")
            except Exception as e:
                logger.warning(f"⚠️ V6 fehlgeschlagen: {e}")
                import traceback
                logger.debug(traceback.format_exc())

        # STUFE 3: Sewing Converter (V1) - Letzter Fallback
        if self.use_v1_fallback and not solid:
            logger.info("🔍 Stufe 3: Sewing Converter (V1) - Letzter Fallback...")
            try:
                from modeling.mesh_converter import MeshToBREPConverter

                converter_v1 = MeshToBREPConverter()

                # Versuche zuerst "mechanical" (direktes Sewing), dann "organic" (SDF)
                result = converter_v1.convert(mesh, target_faces=3000, method="mechanical")

                if result:
                    logger.success(f"✅ V1 Sewing erfolgreich (Typ: {type(result).__name__})")
                    method_used = "V1 (Sewing Fallback)"
                    return result
                else:
                    logger.error("❌ V1 Sewing fehlgeschlagen (gab None zurück)")

            except ImportError as e:
                logger.error(f"❌ V1 nicht verfügbar: {e}")
            except Exception as e:
                logger.error(f"❌ V1 fehlgeschlagen: {e}")
                import traceback
                logger.debug(traceback.format_exc())

        # Alle Methoden fehlgeschlagen
        if not solid:
            logger.error("❌ Alle Konvertierungsmethoden fehlgeschlagen")
            return None

        logger.success(f"✅ Hybrid-Conversion erfolgreich mit: {method_used}")
        return solid

    def _try_ransac(self, converter, mesh: 'pv.PolyData'):
        """
        Versucht RANSAC-Conversion und gibt (solid, coverage) zurück.

        Returns:
            (Solid, Coverage-Ratio) oder (None, 0.0)
        """
        try:
            # Mesh vorbereiten
            if 'Normals' not in mesh.cell_data:
                mesh = mesh.compute_normals(cell_normals=True, point_normals=False)

            # Regionen segmentieren
            regions = converter._segment_regions(mesh)

            if len(regions) == 0:
                return None, 0.0

            # Pro Region: Primitive fitten
            primitives = []
            total_points = 0
            covered_points = 0

            for region_id, cell_ids in regions.items():
                points = converter._extract_region_points(mesh, cell_ids)
                total_points += len(points)

                if len(points) < 10:
                    continue

                primitive = converter._fit_primitive(points, mesh, cell_ids)
                if primitive:
                    primitives.append(primitive)
                    covered_points += len(primitive.points)

            # Coverage berechnen
            coverage = covered_points / total_points if total_points > 0 else 0.0

            # Nur wenn genug Primitives erkannt wurden
            if len(primitives) == 0:
                return None, 0.0

            # Solid erstellen
            try:
                from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing

                sewer = BRepBuilderAPI_Sewing(converter.sewing_tol)
                face_count = 0

                for prim in primitives:
                    try:
                        ocp_face = converter._primitive_to_face(prim)
                        if ocp_face and not ocp_face.IsNull():
                            sewer.Add(ocp_face)
                            face_count += 1
                    except Exception as e:
                        logger.debug(f"Face-Erstellung fehlgeschlagen: {e}")

                if face_count == 0:
                    return None, coverage

                sewer.Perform()
                sewed_shape = sewer.SewedShape()

                if sewed_shape.IsNull():
                    return None, coverage

                solid = converter._shape_to_solid(sewed_shape)
                return solid, coverage

            except Exception as e:
                logger.debug(f"Solid-Erstellung fehlgeschlagen: {e}")
                return None, coverage

        except Exception as e:
            logger.debug(f"RANSAC-Try fehlgeschlagen: {e}")
            return None, 0.0

    def get_stats(self) -> dict:
        """Gibt Statistiken über den letzten Conversion-Lauf zurück"""
        return {
            "v7_enabled": self.use_v7,
            "v6_fallback_enabled": self.use_v6_fallback,
            "v1_fallback_enabled": self.use_v1_fallback,
            "min_coverage": self.min_coverage
        }
