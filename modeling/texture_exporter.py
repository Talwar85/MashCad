"""
Texture Exporter - Wendet Surface-Texturen beim Export als Displacement auf das Mesh an.

KRITISCH: Das BREP wird NIEMALS modifiziert.
Texturen werden NUR auf das tessellierte Export-Mesh angewendet.

Fail-Fast: Bei Fehlern wird eine klare TextureResult mit ERROR zurückgegeben.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Any
from enum import Enum, auto
import numpy as np

from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False


class ResultStatus(Enum):
    """Result-Status nach CLAUDE.md Anti-Schwammig-Policy."""
    SUCCESS = auto()   # Alles OK
    WARNING = auto()   # OK aber mit Einschränkungen
    EMPTY = auto()     # Kein Ergebnis (kein Fehler!)
    ERROR = auto()     # Fehlgeschlagen


@dataclass
class TextureResult:
    """
    Strukturiertes Result für Texture-Operationen.

    Folgt dem Result-Pattern aus CLAUDE.md für klare Fehlerunterscheidung.
    """
    status: ResultStatus
    mesh: Optional[Any] = None  # pv.PolyData
    message: str = ""
    details: dict = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status in (ResultStatus.SUCCESS, ResultStatus.WARNING)

    @property
    def is_error(self) -> bool:
        return self.status == ResultStatus.ERROR


class TextureExporter:
    """
    Wendet Surface-Texturen als Displacement auf Mesh-Faces an.

    Verwendet für Export (STL, 3MF etc.).
    Das Original-Mesh wird NICHT modifiziert - es wird eine Kopie zurückgegeben.
    """

    @staticmethod
    def apply_displacement(
        mesh: Any,
        texture_feature: Any,  # SurfaceTextureFeature
        face_mapping: Any,     # FaceTriangleMapping
    ) -> Tuple[Any, TextureResult]:
        """
        Wendet Displacement NUR auf die Face-Triangles an.

        WICHTIG: Nur die spezifizierten Triangles werden modifiziert!
        Der Rest des Mesh bleibt unverändert.

        Args:
            mesh: PyVista PolyData Mesh
            texture_feature: SurfaceTextureFeature mit Textur-Parametern
            face_mapping: FaceTriangleMapping mit Triangle-Indices

        Returns:
            Tuple (displaced_mesh, TextureResult)
        """
        if not HAS_PYVISTA:
            return mesh, TextureResult(
                status=ResultStatus.ERROR,
                message="PyVista nicht verfügbar"
            )

        if mesh is None:
            return None, TextureResult(
                status=ResultStatus.ERROR,
                message="Mesh ist None"
            )

        if face_mapping is None or not face_mapping.triangle_indices:
            return mesh, TextureResult(
                status=ResultStatus.EMPTY,
                message="Keine Triangles für diese Face"
            )

        try:
            triangle_indices = face_mapping.triangle_indices

            if not triangle_indices:
                return mesh, TextureResult(
                    status=ResultStatus.EMPTY,
                    message="Keine Triangles zu verarbeiten"
                )

            # === SCHRITT 1: Face-Mesh extrahieren ===
            # Nur die Triangles der texturierten Face extrahieren
            # WICHTIG: extract_cells() gibt UnstructuredGrid zurück, wir brauchen PolyData!
            extracted = mesh.extract_cells(triangle_indices)

            if extracted.n_cells == 0:
                return mesh, TextureResult(
                    status=ResultStatus.WARNING,
                    message="Keine Zellen nach Extraktion"
                )

            # Konvertiere UnstructuredGrid zu PolyData
            face_mesh = extracted.extract_surface()

            # === SCHRITT 2: Face-Mesh subdividen ===
            # DYNAMISCH: Berechne benötigte Subdivisions basierend auf Face-Größe und Scale
            # Ziel: Mindestens 4 Vertices pro Textur-Wiederholung
            scale = getattr(texture_feature, 'scale', 2.0)
            base_subdivisions = getattr(texture_feature, 'export_subdivisions', 4)

            # Berechne Face-Größe aus Bounds
            bounds = face_mesh.bounds  # (xmin, xmax, ymin, ymax, zmin, zmax)
            face_size = max(
                bounds[1] - bounds[0],  # X-Ausdehnung
                bounds[3] - bounds[2],  # Y-Ausdehnung
                bounds[5] - bounds[4]   # Z-Ausdehnung
            )

            # Berechne benötigte Vertex-Dichte
            # Bei n Subdivisions: 2^n Segmente pro Kante
            # Wir wollen: face_size / 2^n <= scale / 4 (4 Vertices pro Pattern)
            # Also: 2^n >= face_size * 4 / scale
            # n >= log2(face_size * 4 / scale)
            if scale > 0 and face_size > 0:
                min_subdivisions = int(np.ceil(np.log2(face_size * 4 / scale)))
                subdivisions = max(base_subdivisions, min(min_subdivisions, 7))  # Max 7 (128 Segmente)
            else:
                subdivisions = base_subdivisions

            if subdivisions > 0:
                try:
                    # Triangulate sicherstellen
                    if not face_mesh.is_all_triangles:
                        face_mesh = face_mesh.triangulate()

                    # Wähle Subdivision-Methode basierend auf Flächentyp
                    surface_type = getattr(face_mapping, 'surface_type', 'plane')
                    if surface_type == 'plane':
                        subfilter = 'linear'
                    else:
                        subfilter = 'loop'

                    face_mesh = face_mesh.subdivide(subdivisions, subfilter=subfilter)
                    logger.info(f"Subdivision: {subdivisions}x für {surface_type} "
                               f"(Face={face_size:.1f}mm, Scale={scale}mm, "
                               f"~{face_mesh.n_points} Vertices)")
                except Exception as e:
                    logger.warning(f"Face-Subdivision fehlgeschlagen: {e}")

            # === SCHRITT 3: Normalen für Face-Mesh berechnen ===
            face_mesh.compute_normals(inplace=True)

            # === SCHRITT 4: UVs NUR für Face-Mesh berechnen ===
            uvs = TextureExporter._compute_uvs(
                face_mesh,
                face_mapping.center,
                face_mapping.normal
            )

            # === SCHRITT 5: Height-Map generieren ===
            from modeling.surface_texture import TextureGenerator, sample_heightmap_at_uvs

            # Prüfe ob wave_width angegeben ist (für konsistente Ripples)
            type_params = texture_feature.type_params.copy()
            wave_width = type_params.get("wave_width")
            
            if wave_width and wave_width > 0:
                # Berechne Face-Größe aus UV-Bounds
                u_min, u_max = uvs[:, 0].min(), uvs[:, 0].max()
                v_min, v_max = uvs[:, 1].min(), uvs[:, 1].max()
                face_size = max(u_max - u_min, v_max - v_min)
                
                # Berechne wave_count basierend auf Face-Größe und gewünschter Wellenbreite
                wave_count = face_size / wave_width
                type_params["wave_count"] = wave_count
                logger.debug(f"Ripple: face_size={face_size:.2f}mm, wave_width={wave_width}mm, wave_count={wave_count:.2f}")

            heightmap = TextureGenerator.generate(
                texture_feature.texture_type,
                type_params,
                size=256
            )

            # Heights an UV-Koordinaten sampeln
            heights = sample_heightmap_at_uvs(
                heightmap,
                uvs,
                scale=texture_feature.scale,
                rotation=texture_feature.rotation
            )

            # Debug: Height-Statistik
            logger.debug(f"Heights: min={heights.min():.3f}, max={heights.max():.3f}, "
                        f"mean={heights.mean():.3f}, std={heights.std():.3f}")

            # Invertieren falls gewünscht
            if texture_feature.invert:
                heights = 1.0 - heights

            # === SCHRITT 6: Displacement-Modus bestimmen ===
            # solid_base=True: Keine Löcher, nur positive Erhöhungen (für Top-Faces/3D-Druck)
            # solid_base=False: Bidirektional -0.5 bis +0.5 (für Seiten/Innenflächen)
            solid_base = getattr(texture_feature, 'solid_base', True)
            
            if solid_base:
                # Verschiebe so dass Minimum bei 0 ist (alles positiv, keine Löcher)
                # Das bedeutet: Original-Oberfläche wird zum tiefsten Punkt
                heights_shifted = heights - heights.min()  # Jetzt von 0 bis max
                logger.debug(f"Solid-Base Modus: heights {heights.min():.3f}-{heights.max():.3f} -> 0-{heights_shifted.max():.3f}")
            else:
                # Bidirektional: -0.5 bis +0.5 (Täler UND Erhöhungen)
                heights_shifted = heights - 0.5
                logger.debug(f"Bidirektionaler Modus: heights {heights.min():.3f}-{heights.max():.3f} -> {heights_shifted.min():.3f}-{heights_shifted.max():.3f}")

            depth = texture_feature.depth
            normals = face_mesh.point_data.get('Normals')

            if normals is None:
                # Fallback: Verwende Face-Normale
                normal_arr = np.array(face_mapping.normal)
                normals = np.tile(normal_arr, (face_mesh.n_points, 1))

            # Displacement anwenden
            displacement = heights_shifted * depth
            logger.debug(f"Displacement: min={displacement.min():.3f}mm, max={displacement.max():.3f}mm")

            face_mesh.points = face_mesh.points + normals * displacement[:, np.newaxis]

            # === SCHRITT 7: Restliches Mesh extrahieren (ohne die texturierten Triangles) ===
            all_indices = set(range(mesh.n_cells))
            remaining_indices = list(all_indices - set(triangle_indices))

            if remaining_indices:
                # extract_cells gibt UnstructuredGrid zurück -> zu PolyData konvertieren
                remaining_extracted = mesh.extract_cells(remaining_indices)
                remaining_mesh = remaining_extracted.extract_surface()
                # Merged: Restliches Mesh + Displaced Face-Mesh
                result_mesh = remaining_mesh.merge(face_mesh)
            else:
                # Gesamtes Mesh war die Face
                result_mesh = face_mesh

            # Normalen für finales Mesh neu berechnen (nur wenn PolyData)
            if hasattr(result_mesh, 'compute_normals'):
                result_mesh.compute_normals(inplace=True)

            return result_mesh, TextureResult(
                status=ResultStatus.SUCCESS,
                mesh=result_mesh,
                message=f"Displacement angewendet: {face_mesh.n_points} Vertices, "
                       f"Typ={texture_feature.texture_type}, Tiefe={depth}mm",
                details={
                    "vertices_affected": face_mesh.n_points,
                    "texture_type": texture_feature.texture_type,
                    "depth": depth,
                    "scale": texture_feature.scale,
                }
            )

        except Exception as e:
            logger.error(f"TextureExporter Fehler: {e}")
            import traceback
            traceback.print_exc()
            return mesh, TextureResult(
                status=ResultStatus.ERROR,
                message=f"Displacement fehlgeschlagen: {str(e)}"
            )

    @staticmethod
    def _compute_uvs(
        mesh: Any,
        face_center: Tuple[float, float, float],
        face_normal: Tuple[float, float, float]
    ) -> np.ndarray:
        """
        Berechnet UV-Koordinaten für alle Mesh-Vertices.

        Projiziert die 3D-Punkte auf die Face-Ebene.

        Args:
            mesh: PyVista Mesh
            face_center: Zentrum der Face (für Ursprung)
            face_normal: Normale der Face (für Projektion)

        Returns:
            UV-Koordinaten Array (N, 2)
        """
        points = mesh.points
        n_points = len(points)

        # Face-Ebene Basis berechnen
        origin = np.array(face_center)
        normal = np.array(face_normal)
        normal = normal / np.linalg.norm(normal)

        # Lokale X-Achse (senkrecht zu Normal)
        if abs(normal[2]) < 0.9:
            local_x = np.cross(normal, [0, 0, 1])
        else:
            local_x = np.cross(normal, [1, 0, 0])
        local_x = local_x / np.linalg.norm(local_x)

        # Lokale Y-Achse (MUSS normalisiert werden!)
        local_y = np.cross(normal, local_x)
        local_y = local_y / np.linalg.norm(local_y)

        # Punkte relativ zum Ursprung
        relative = points - origin

        # Projektion auf lokale Achsen
        u = np.dot(relative, local_x)
        v = np.dot(relative, local_y)

        return np.column_stack([u, v])


def apply_textures_to_body(
    mesh: Any,
    body: Any,
    face_mappings: List[Any]
) -> Tuple[Any, List[TextureResult]]:
    """
    Wendet alle SurfaceTextureFeatures eines Bodies auf das Mesh an.

    WICHTIG: Alle Texturen werden aus dem ORIGINAL-Mesh extrahiert,
    dann am Ende zusammengemerged. Das verhindert Index-Verschiebungen!

    Args:
        mesh: PyVista PolyData Mesh
        body: Body Objekt mit features Liste
        face_mappings: Liste von FaceTriangleMapping

    Returns:
        Tuple (processed_mesh, results_list)
    """
    from modeling import SurfaceTextureFeature
    from modeling.textured_tessellator import find_matching_mapping

    results = []

    # Sammle alle zu texturierenden Triangle-Indices und deren displaced Meshes
    all_textured_indices = set()
    displaced_face_meshes = []
    mapping_by_face_index = {
        int(mapping.face_index): mapping
        for mapping in face_mappings
        if hasattr(mapping, "face_index")
    }

    def _add_mapping(face_idx: int, selected_mappings: List[Any], seen_face_indices: set) -> bool:
        mapping = mapping_by_face_index.get(int(face_idx))
        if mapping is None or int(face_idx) in seen_face_indices:
            return False
        selected_mappings.append(mapping)
        seen_face_indices.add(int(face_idx))
        return True

    # PHASE 1: Alle Texturen aus dem ORIGINAL-Mesh extrahieren und verarbeiten
    for feature in body.features:
        if not isinstance(feature, SurfaceTextureFeature):
            continue

        if feature.suppressed:
            continue

        selected_mappings = []
        seen_face_indices = set()
        has_topological_refs = bool(
            (getattr(feature, "face_indices", []) or [])
            or (getattr(feature, "face_shape_ids", []) or [])
        )

        # TNP v4.0 primary: Face-Indizes direkt auf Mappings auflösen.
        for raw_idx in getattr(feature, "face_indices", []) or []:
            try:
                face_idx = int(raw_idx)
            except Exception:
                continue
            _add_mapping(face_idx, selected_mappings, seen_face_indices)

        # TNP v4.0 secondary: ShapeIDs -> FaceIndex -> Mapping.
        if not selected_mappings and getattr(feature, "face_shape_ids", []):
            shape_service = None
            if getattr(body, "_document", None) is not None:
                shape_service = getattr(body._document, "_shape_naming_service", None)
            solid = getattr(body, "_build123d_solid", None)

            if shape_service is not None and solid is not None:
                try:
                    from build123d import Face
                    from modeling.topology_indexing import face_index_of

                    ocp_solid = solid.wrapped if hasattr(solid, "wrapped") else solid
                    for shape_id in getattr(feature, "face_shape_ids", []) or []:
                        if not hasattr(shape_id, "uuid"):
                            continue
                        try:
                            resolved_ocp, _method = shape_service.resolve_shape_with_method(
                                shape_id,
                                ocp_solid,
                                log_unresolved=False,
                            )
                        except Exception:
                            continue
                        if resolved_ocp is None:
                            continue
                        try:
                            face_idx = face_index_of(solid, Face(resolved_ocp))
                        except Exception:
                            face_idx = None
                        if face_idx is None:
                            continue
                        _add_mapping(int(face_idx), selected_mappings, seen_face_indices)
                except Exception:
                    pass

        # Legacy/Recovery: nur wenn KEINE topologischen Referenzen vorhanden sind.
        if not selected_mappings and not has_topological_refs:
            for selector in feature.face_selectors:
                mapping = find_matching_mapping(selector, face_mappings)
                if mapping is None:
                    continue
                face_idx = int(getattr(mapping, "face_index", -1))
                if face_idx in seen_face_indices:
                    continue
                selected_mappings.append(mapping)
                seen_face_indices.add(face_idx)

        if not selected_mappings:
            if has_topological_refs:
                warning_msg = f"TNP-Referenz nicht auflösbar für Textur '{feature.name}'"
            else:
                warning_msg = f"Face nicht gefunden für Textur '{feature.name}'"
            results.append(TextureResult(
                status=ResultStatus.WARNING,
                message=warning_msg,
            ))
            continue

        for mapping in selected_mappings:

            # Triangle-Indices merken
            triangle_indices = mapping.triangle_indices
            if not triangle_indices:
                results.append(TextureResult(
                    status=ResultStatus.EMPTY,
                    message=f"Keine Triangles für Face"
                ))
                continue

            # Extrahiere Face-Mesh direkt aus ORIGINAL
            try:
                extracted = mesh.extract_cells(triangle_indices)
                if extracted.n_cells == 0:
                    results.append(TextureResult(
                        status=ResultStatus.WARNING,
                        message=f"Keine Zellen nach Extraktion"
                    ))
                    continue

                face_mesh = extracted.extract_surface()

                # Displacement anwenden
                displaced_mesh = _apply_displacement_to_face(
                    face_mesh, feature, mapping
                )

                if displaced_mesh is not None:
                    displaced_face_meshes.append(displaced_mesh)
                    all_textured_indices.update(triangle_indices)
                    results.append(TextureResult(
                        status=ResultStatus.SUCCESS,
                        mesh=displaced_mesh,
                        message=f"Textur '{feature.name}' angewendet",
                        details={
                            "vertices": displaced_mesh.n_points,
                            "texture_type": feature.texture_type
                        }
                    ))
                else:
                    results.append(TextureResult(
                        status=ResultStatus.ERROR,
                        message=f"Displacement fehlgeschlagen für '{feature.name}'"
                    ))

            except Exception as e:
                logger.error(f"Face-Extraktion fehlgeschlagen: {e}")
                results.append(TextureResult(
                    status=ResultStatus.ERROR,
                    message=f"Extraktion fehlgeschlagen: {e}"
                ))

    # PHASE 2: Restliches Mesh (ohne texturierte Triangles) extrahieren
    if not all_textured_indices:
        # Keine Texturen angewendet
        return mesh, results

    all_indices = set(range(mesh.n_cells))
    remaining_indices = list(all_indices - all_textured_indices)

    if remaining_indices:
        remaining_extracted = mesh.extract_cells(remaining_indices)
        remaining_mesh = remaining_extracted.extract_surface()
    else:
        remaining_mesh = None

    # PHASE 3: Alles zusammenmergen
    if displaced_face_meshes:
        # Starte mit remaining_mesh oder erstem displaced
        if remaining_mesh is not None:
            final_mesh = remaining_mesh
            for displaced_mesh in displaced_face_meshes:
                final_mesh = final_mesh.merge(displaced_mesh)
        else:
            final_mesh = displaced_face_meshes[0]
            for displaced_mesh in displaced_face_meshes[1:]:
                final_mesh = final_mesh.merge(displaced_mesh)

        # Normalen neu berechnen
        if hasattr(final_mesh, 'compute_normals'):
            final_mesh.compute_normals(inplace=True)

        logger.info(f"Texturen angewendet: {len(all_textured_indices)} Triangles texturiert, "
                   f"{len(displaced_face_meshes)} Faces verarbeitet")

        return final_mesh, results

    return mesh, results


def _apply_displacement_to_face(
    face_mesh: Any,
    texture_feature: Any,
    face_mapping: Any
) -> Optional[Any]:
    """
    Wendet Displacement direkt auf ein Face-Mesh an.

    Separate Funktion für die Phase-2 Verarbeitung.
    """
    try:
        import pyvista as pv
        from modeling.surface_texture import TextureGenerator, sample_heightmap_at_uvs

        scale = getattr(texture_feature, 'scale', 2.0)
        base_subdivisions = getattr(texture_feature, 'export_subdivisions', 4)

        # Face-Größe aus Mapping-Area berechnen (robuster als bounds!)
        mapping_area = getattr(face_mapping, 'area', 0)
        if mapping_area > 0:
            # Für rechteckige Flächen: Diagonale ≈ sqrt(2 * area)
            face_size = np.sqrt(mapping_area)
        else:
            # Fallback: Bounds
            bounds = face_mesh.bounds
            face_size = max(
                bounds[1] - bounds[0],
                bounds[3] - bounds[2],
                bounds[5] - bounds[4]
            )

        # Berechne benötigte Subdivisions
        if scale > 0 and face_size > 0:
            min_subdivisions = int(np.ceil(np.log2(face_size * 4 / scale)))
            subdivisions = max(base_subdivisions, min(min_subdivisions, 7))
        else:
            subdivisions = base_subdivisions

        # Subdivision
        if subdivisions > 0:
            if not face_mesh.is_all_triangles:
                face_mesh = face_mesh.triangulate()

            surface_type = getattr(face_mapping, 'surface_type', 'plane')
            subfilter = 'linear' if surface_type == 'plane' else 'loop'

            face_mesh = face_mesh.subdivide(subdivisions, subfilter=subfilter)
            logger.info(f"Displacement: {subdivisions}x Subdivision für {surface_type} "
                       f"(Area={mapping_area:.1f}mm², Size≈{face_size:.1f}mm, "
                       f"~{face_mesh.n_points} Vertices)")

        # Normalen berechnen
        face_mesh.compute_normals(inplace=True)

        # UVs berechnen
        uvs = TextureExporter._compute_uvs(
            face_mesh,
            face_mapping.center,
            face_mapping.normal
        )

        # Height-Map generieren
        heightmap = TextureGenerator.generate(
            texture_feature.texture_type,
            texture_feature.type_params,
            size=256
        )

        # Heights sampeln
        heights = sample_heightmap_at_uvs(
            heightmap,
            uvs,
            scale=texture_feature.scale,
            rotation=texture_feature.rotation
        )

        # Invertieren falls gewünscht
        if texture_feature.invert:
            heights = 1.0 - heights

        # WICHTIG: Heights zentrieren für bidirektionales Displacement
        # Statt nur 0->1 (nur Erhöhungen) machen wir -0.5->+0.5 (Täler UND Erhöhungen)
        heights_centered = heights - 0.5

        # Displacement anwenden
        depth = texture_feature.depth
        normals = face_mesh.point_data.get('Normals')

        if normals is None:
            normal_arr = np.array(face_mapping.normal)
            normals = np.tile(normal_arr, (face_mesh.n_points, 1))

        displacement = heights_centered * depth
        logger.debug(f"Heights: min={heights.min():.3f}, max={heights.max():.3f}, "
                    f"std={heights.std():.3f}")
        logger.debug(f"Displacement (centered): min={displacement.min():.3f}mm, max={displacement.max():.3f}mm")

        face_mesh.points = face_mesh.points + normals * displacement[:, np.newaxis]

        return face_mesh

    except Exception as e:
        logger.error(f"_apply_displacement_to_face Fehler: {e}")
        import traceback
        traceback.print_exc()
        return None
