"""
Document - Dokument mit optionalem Assembly-System

Phase 1 Assembly: Unterstützt hierarchische Component-Struktur.
Backward-compatible: Alte Projekte laden weiterhin korrekt.
"""

from dataclasses import asdict, dataclass, field
import tempfile
from typing import List, Optional, Tuple, Union, Any
from enum import Enum, auto
import math
import uuid
import sys
import os
import traceback
from loguru import logger

# Core imports
from config.feature_flags import is_enabled

# Import Body from new location
from modeling.body import Body

# Import Component from new location
from modeling.component import Component

# Feature imports
from modeling.features.base import Feature, FeatureType
from modeling.features.extrude import ExtrudeFeature, PushPullFeature
from modeling.features.fillet_chamfer import FilletFeature, ChamferFeature
from modeling.features.revolve import RevolveFeature
from modeling.features.pattern import PatternFeature
from modeling.features.transform import TransformFeature
from modeling.features.boolean import BooleanFeature
from modeling.features.import_feature import ImportFeature
from modeling.features.advanced import (
    LoftFeature, SweepFeature, ShellFeature, HoleFeature,
    DraftFeature, SplitFeature, ThreadFeature, HollowFeature,
    NSidedPatchFeature, SurfaceTextureFeature, PrimitiveFeature,
    LatticeFeature
)
from modeling.features.import_feature import ImportFeature
from modeling.construction import ConstructionPlane

# Sketch import
from sketcher import Sketch


# For SplitResult
from dataclasses import dataclass
from typing import Any

@dataclass
class SplitResult:
    """Result of a Split Body operation (keep_both=True)"""
    body_above: Any
    body_below: Any
    split_plane: dict


class Document:
    """
    Dokument mit optionalem Assembly-System.

    Phase 1 Assembly: UnterstÃ¼tzt hierarchische Component-Struktur.
    Backward-compatible: Alte Projekte laden weiterhin korrekt.
    """

    def __init__(self, name="Doc"):
        self.name = name
        self.active_body: Optional[Body] = None
        self.active_sketch: Optional[Sketch] = None
        
        # TNP v4.0: Shape Naming Service fÃ¼r persistente Shape-Referenzen
        from modeling.tnp_system import ShapeNamingService
        self._shape_naming_service = ShapeNamingService()
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"TNP v4.0: ShapeNamingService initialisiert fÃ¼r '{name}'")

        # =========================================================================
        # Assembly System (Phase 1) - Permanent aktiviert
        # =========================================================================
        # Backward-Compatibility: Viele GUI-Pfade prüfen weiterhin dieses Flag.
        self._assembly_enabled = True

        # Component-basierte Architektur
        self.root_component: Component = Component(name="Root")
        self.root_component.is_active = True
        self._active_component: Optional[Component] = self.root_component
        logger.info(f"[ASSEMBLY] Component-System aktiviert fuer '{name}'")

    # =========================================================================
    # Properties - Delegieren zu active_component
    # =========================================================================

    @property
    def bodies(self) -> List[Body]:
        """Bodies der aktiven Component."""
        if self._active_component:
            return self._active_component.bodies
        return []

    @bodies.setter
    def bodies(self, value: List[Body]):
        if self._active_component:
            self._active_component.bodies = value

    @property
    def sketches(self) -> List[Sketch]:
        """Sketches der aktiven Component."""
        if self._active_component:
            return self._active_component.sketches
        return []

    @sketches.setter
    def sketches(self, value: List[Sketch]):
        if self._active_component:
            self._active_component.sketches = value

    @property
    def planes(self) -> List[ConstructionPlane]:
        """Planes der aktiven Component."""
        if self._active_component:
            return self._active_component.planes
        return []

    @planes.setter
    def planes(self, value: List[ConstructionPlane]):
        if self._active_component:
            self._active_component.planes = value

    # =========================================================================
    # Assembly-spezifische Methoden
    # =========================================================================

    @property
    def active_component(self) -> Optional[Component]:
        """Gibt die aktive Component zurÃ¼ck."""
        return self._active_component

    def set_active_component(self, comp: Component) -> bool:
        """
        Setzt die aktive Component.

        Args:
            comp: Zu aktivierende Component

        Returns:
            True wenn erfolgreich
        """
        if self._active_component:
            self._active_component.is_active = False

        self._active_component = comp
        comp.is_active = True
        logger.info(f"[ASSEMBLY] Aktive Component: {comp.name}")
        return True

    def get_all_bodies(self) -> List[Body]:
        """
        Gibt alle Bodies im Dokument zurÃ¼ck (rekursiv).

        Returns:
            Liste aller Bodies
        """
        if self.root_component:
            return self.root_component.get_all_bodies(recursive=True)
        return []

    def get_all_sketches(self) -> List[Sketch]:
        """Gibt alle Sketches im Dokument zurÃ¼ck (rekursiv)."""
        if self.root_component:
            return self.root_component.get_all_sketches(recursive=True)
        return []

    def find_body_by_id(self, body_id: str) -> Optional[Body]:
        """Findet Body nach ID (rekursiv)."""
        if self.root_component:
            return self.root_component.find_body_by_id(body_id)
        return None

    def new_component(self, name: str = None, parent: Component = None) -> Optional[Component]:
        """
        Erstellt neue Component.

        Args:
            name: Name der neuen Component
            parent: Parent-Component (default: active_component)

        Returns:
            Neue Component
        """
        parent = parent or self._active_component or self.root_component
        return parent.add_sub_component(name)

    def new_body(self, name=None):
        b = Body(name or f"Body{len(self.bodies)+1}", document=self)
        self.add_body(b, set_active=True)
        return b

    def add_body(self, body: Body, component: Component = None, set_active: bool = False):
        """FÃ¼gt einen Body dem Dokument hinzu und setzt die Document-Referenz."""
        if body is None:
            return None

        body._document = self

        target = component or self._active_component or self.root_component
        if target and body not in target.bodies:
            target.bodies.append(body)

        if set_active:
            self.active_body = body

        return body

    def new_sketch(self, name=None):
        s = Sketch(name or f"Sketch{len(self.sketches)+1}")
        self.sketches.append(s)
        self.active_sketch = s
        return s

    def split_body(self, body: Body, plane_origin: tuple, plane_normal: tuple) -> Tuple[Body, Body]:
        """
        Teilt einen Body in 2 HÃ¤lften und fÃ¼gt beide zum Document hinzu.

        Multi-Body Split Architecture (AGENTS.md Phase 3):
        - Erstellt SplitFeature mit keep_side="both"
        - Beide Bodies erhalten shared Feature-Historie
        - Original-Body wird aus Document entfernt
        - Beide neue Bodies werden registriert

        Args:
            body: Zu teilender Body
            plane_origin: Ursprung der Split-Ebene (x, y, z)
            plane_normal: Normale der Split-Ebene (x, y, z)

        Returns:
            (body_above, body_below) - beide Bodies im Document registriert

        Raises:
            ValueError: Wenn Split fehlschlÃ¤gt
        """
        from build123d import Solid

        # 1. Split-Feature erstellen
        split_feat = SplitFeature(
            plane_origin=plane_origin,
            plane_normal=plane_normal,
            keep_side="both"  # Explizit beide behalten
        )

        # 2. Feature zu Original-Body hinzufÃ¼gen (ohne Rebuild - wir wollen SplitResult)
        body.features.append(split_feat)
        split_index = len(body.features) - 1

        # 3. _compute_split aufrufen â†’ SplitResult
        try:
            split_result = body._compute_split(split_feat, body._build123d_solid)
        except Exception as e:
            # Rollback: Feature wieder entfernen
            body.features.pop()
            raise ValueError(f"Split-Operation fehlgeschlagen: {e}")

        # Validierung: Muss SplitResult sein
        if not isinstance(split_result, SplitResult):
            body.features.pop()
            raise ValueError("Split mit keep_side='both' muss SplitResult zurÃ¼ckgeben")

        # 4. Beide Bodies erstellen mit shared history
        body_above = Body(name=f"{body.name}_above", document=self)
        body_above.features = body.features.copy()  # Shared history
        body_above._build123d_solid = split_result.body_above
        body_above.source_body_id = body.id
        body_above.split_index = split_index
        body_above.split_side = "above"

        body_below = Body(name=f"{body.name}_below", document=self)
        body_below.features = body.features.copy()  # Shared history
        body_below._build123d_solid = split_result.body_below
        body_below.source_body_id = body.id
        body_below.split_index = split_index
        body_below.split_side = "below"

        # 5. Original-Body aus Document entfernen
        if body in self.bodies:
            self.bodies.remove(body)
            logger.debug(f"Split: Original-Body '{body.name}' entfernt")

        # 6. Beide neue Bodies hinzufÃ¼gen
        self.add_body(body_above, set_active=False)
        self.add_body(body_below, set_active=False)

        # Invalidate meshes fÃ¼r beide Bodies
        body_above.invalidate_mesh()
        body_below.invalidate_mesh()

        logger.debug(f"Split: '{body.name}' â†’ '{body_above.name}' + '{body_below.name}'")

        # 7. Setze einen der Bodies als aktiv (optional - user kann das auch manuell machen)
        if self.active_body == body:
            self.active_body = body_above

        return body_above, body_below

    def new_plane(self, base: str = "XY", offset: float = 0.0, name: str = None):
        """
        Erstellt neue Konstruktionsebene.

        Args:
            base: Basis-Ebene ("XY", "XZ", "YZ")
            offset: Abstand in mm
            name: Optional - sonst automatisch generiert

        Returns:
            ConstructionPlane
        """
        plane = ConstructionPlane.from_offset(base, offset, name)
        self.planes.append(plane)
        logger.info(f"Konstruktionsebene erstellt: {plane.name}")
        return plane

    def find_plane_by_id(self, plane_id: str) -> Optional[ConstructionPlane]:
        """Findet Konstruktionsebene nach ID."""
        for p in self.planes:
            if p.id == plane_id:
                return p
        return None

    # =========================================================================
    # Phase 8.3: STEP Import/Export
    # =========================================================================

    def export_step(self, filename: str, schema: str = "AP214") -> bool:
        """
        Exportiert gesamtes Dokument als STEP-Datei.

        Args:
            filename: Ausgabepfad (.step/.stp)
            schema: "AP214" (Standard) oder "AP242" (PMI)

        Returns:
            True bei Erfolg
        """
        from modeling.step_io import STEPWriter, STEPSchema

        # Schema konvertieren
        schema_enum = STEPSchema.AP242 if schema == "AP242" else STEPSchema.AP214

        # Bodies mit Solids sammeln
        export_bodies = [b for b in self.bodies if hasattr(b, '_build123d_solid') and b._build123d_solid]

        if not export_bodies:
            logger.warning("Keine Bodies mit BREP-Daten zum Exportieren")
            return False

        if len(export_bodies) == 1:
            # Einzelner Body
            result = STEPWriter.export_solid(
                export_bodies[0]._build123d_solid,
                filename,
                application_name="MashCad",
                schema=schema_enum
            )
        else:
            # Multi-Body Assembly
            result = STEPWriter.export_assembly(
                export_bodies,
                filename,
                assembly_name=self.name,
                schema=schema_enum
            )

        if not result.success:
            logger.error(f"STEP Export fehlgeschlagen: {result.message}")

        return result.success

    def import_step(self, filename: str, auto_heal: bool = True) -> List['Body']:
        """
        Importiert STEP-Datei und erstellt neue Bodies.

        Args:
            filename: Pfad zur STEP-Datei
            auto_heal: Automatisches Geometry-Healing

        Returns:
            Liste der erstellten Bodies (leer bei Fehler)
        """
        from modeling.step_io import STEPReader

        result = STEPReader.import_file(filename, auto_heal=auto_heal)

        if not result.success:
            for error in result.errors:
                logger.error(f"STEP Import: {error}")
            return []

        # Warnings loggen
        for warning in result.warnings:
            logger.warning(f"STEP Import: {warning}")

        # Bodies erstellen
        new_bodies = []
        for i, solid in enumerate(result.solids):
            body = Body(name=f"Imported_{i+1}", document=self)
            body._build123d_solid = solid
            body._update_mesh_from_solid(solid)

            self.add_body(body, set_active=False)
            new_bodies.append(body)

        if new_bodies:
            self.active_body = new_bodies[0]
            logger.debug(f"STEP Import: {len(new_bodies)} Body(s) erstellt")

        return new_bodies

    # =========================================================================
    # Phase 8.2: Persistente Projekt-Speicherung
    # =========================================================================

    def to_dict(self) -> dict:
        """
        Serialisiert gesamtes Dokument zu Dictionary.

        Persistiert immer im Component-basierten Format (v9+).

        Returns:
            Dictionary fÃ¼r JSON-Serialisierung
        """
        # Parameter speichern
        try:
            from core.parameters import get_parameters
            params = get_parameters()
            params_data = params.to_dict() if params else {}
        except ImportError:
            params_data = {}

        root_component_data = self._build_root_component_payload()
        active_component_id = self._active_component.id if self._active_component else root_component_data.get("id")

        return {
            "version": "9.1",
            "name": self.name,
            "parameters": params_data,
            "assembly_enabled": True,
            "root_component": root_component_data,
            "active_component_id": active_component_id,
            "active_body_id": self.active_body.id if self.active_body else None,
            "active_sketch_id": self.active_sketch.id if self.active_sketch else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Document':
        """
        Deserialisiert Dokument aus Dictionary.

        LÃ¤dt primÃ¤r Component-Format (v9+). Flat-Format-Daten werden
        on-the-fly in eine Root-Component migriert.

        Args:
            data: Dictionary mit Dokument-Daten

        Returns:
            Neues Document-Objekt
        """
        doc = cls(name=data.get("name", "Imported"))
        version = data.get("version", "unknown")

        # Parameter laden
        if "parameters" in data:
            try:
                from core.parameters import get_parameters
                params = get_parameters()
                params.from_dict(data["parameters"])
                logger.info(f"Parameter geladen: {len(params.list_all())} Variablen")
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"Parameter konnten nicht geladen werden: {e}")

        payload = dict(data)
        if "root_component" not in payload:
            payload["root_component"] = cls._migrate_flat_document_payload(data)
            payload["assembly_enabled"] = True
            payload.setdefault("active_component_id", payload["root_component"].get("id"))
            logger.info(f"[MIGRATION] Flat-Format v{version} zu Root-Component migriert")

        stripped_legacy, converted_legacy = cls._migrate_legacy_nsided_payload(payload)
        if stripped_legacy > 0:
            logger.info(
                f"[MIGRATION] NSided legacy edge_selectors entfernt: {stripped_legacy} "
                f"(zu geometric_selectors konvertiert: {converted_legacy})"
            )

        logger.info(f"[ASSEMBLY] Lade Component-Format v{version}")
        doc._load_assembly_format(payload)

        # KRITISCH fÃ¼r parametrisches CAD: Sketch-Referenzen in Features wiederherstellen
        doc._restore_sketch_references()

        # Logging
        total_bodies = len(doc.get_all_bodies())
        total_sketches = len(doc.get_all_sketches())
        logger.info(f"Projekt geladen: {total_bodies} Bodies, {total_sketches} Sketches")
        return doc

    def _load_assembly_format(self, data: dict):
        """LÃ¤dt Dokument aus Assembly-Format (v9.0+)."""
        # Root Component laden
        root_data = data.get("root_component", {})
        if root_data:
            self.root_component = Component.from_dict(root_data)
        else:
            self.root_component = Component(name="Root")

        self._active_component = self.root_component  # Default

        # Aktive Component wiederherstellen
        active_comp_id = data.get("active_component_id")
        if active_comp_id:
            found = self.root_component.find_component_by_id(active_comp_id)
            if found:
                self._active_component = found
                found.is_active = True
                logger.debug(f"[ASSEMBLY] Aktive Component wiederhergestellt: {found.name}")

        # Aktive Auswahl wiederherstellen
        active_body_id = data.get("active_body_id")
        if active_body_id:
            self.active_body = self.find_body_by_id(active_body_id)

        active_sketch_id = data.get("active_sketch_id")
        if active_sketch_id:
            all_sketches = self.get_all_sketches()
            self.active_sketch = next((s for s in all_sketches if s.id == active_sketch_id), None)

        # Bodies an Document anbinden (TNP v4.0)
        self._attach_document_to_bodies()

    def _build_root_component_payload(self) -> dict:
        """
        Liefert serialisierbare Root-Component-Daten.
        """
        if self.root_component:
            return self.root_component.to_dict()

        return {
            "id": "root",
            "name": "Root",
            "position": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "visible": True,
            "is_active": True,
            "expanded": True,
            "bodies": [],
            "sketches": [],
            "planes": [],
            "sub_components": [],
        }

    @staticmethod
    def _migrate_flat_document_payload(data: dict) -> dict:
        """
        Migriert altes Flat-Dokumentformat in eine Root-Component-Struktur.
        """
        return {
            "id": "root",
            "name": "Root",
            "position": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "visible": True,
            "is_active": True,
            "expanded": True,
            "bodies": data.get("bodies", []),
            "sketches": data.get("sketches", []),
            "planes": data.get("planes", []),
            "sub_components": [],
        }

    @staticmethod
    def _iter_component_payloads(component_data: dict):
        """Iteriert rekursiv Ã¼ber Component-Dicts eines Payloads."""
        if not isinstance(component_data, dict):
            return
        yield component_data
        for sub in component_data.get("sub_components", []) or []:
            yield from Document._iter_component_payloads(sub)

    @staticmethod
    def _migrate_legacy_nsided_payload(payload: dict) -> Tuple[int, int]:
        """
        Entfernt legacy NSided edge_selectors aus dem Payload und konvertiert sie.

        Returns:
            (stripped_count, converted_count)
        """
        root = payload.get("root_component")
        if not isinstance(root, dict):
            return 0, 0

        stripped_count = 0
        converted_count = 0

        for comp in Document._iter_component_payloads(root):
            for body_data in comp.get("bodies", []) or []:
                for feat_data in body_data.get("features", []) or []:
                    if feat_data.get("feature_class") != "NSidedPatchFeature":
                        continue

                    legacy = feat_data.pop("edge_selectors", None)
                    if legacy is None:
                        continue
                    stripped_count += 1

                    has_modern_refs = bool(
                        feat_data.get("edge_indices")
                        or feat_data.get("edge_shape_ids")
                        or feat_data.get("geometric_selectors")
                    )
                    if has_modern_refs:
                        continue

                    migrated_geo = Body._convert_legacy_nsided_edge_selectors(legacy)
                    if migrated_geo:
                        feat_data["geometric_selectors"] = migrated_geo
                        converted_count += 1

        return stripped_count, converted_count

    def _attach_document_to_bodies(self):
        """Stellt sicher, dass alle Bodies eine Document-Referenz haben."""
        for body in self.get_all_bodies():
            body._document = self

    def _restore_sketch_references(self):
        """
        Stellt Sketch-Referenzen in Features wieder her (nach dem Laden).
        ErmÃ¶glicht parametrische Updates wenn Sketches geÃ¤ndert werden.

        Funktioniert mit beiden Modi (Legacy und Assembly).
        """
        # Alle Sketches sammeln (rekursiv bei Assembly)
        all_sketches = self.get_all_sketches()
        sketch_map = {s.id: s for s in all_sketches}
        restored_count = 0

        # Alle Bodies durchgehen (rekursiv bei Assembly)
        all_bodies = self.get_all_bodies()
        for body in all_bodies:
            for feature in body.features:
                sketch_id = getattr(feature, '_sketch_id', None)
                if sketch_id and sketch_id in sketch_map:
                    feature.sketch = sketch_map[sketch_id]
                    restored_count += 1
                    logger.debug(f"Sketch-Referenz wiederhergestellt: {feature.name} â†’ {sketch_map[sketch_id].name}")

        if restored_count > 0:
            logger.info(f"[PARAMETRIC] {restored_count} Sketch-Referenzen wiederhergestellt")

    def _migrate_loaded_nsided_features_to_indices(self) -> int:
        """
        Einmalige Laufzeitmigration: NSided-Features auf edge_indices/ShapeIDs heben.

        Nutzt vorhandene geometric_selectors und das aktuelle Body-Solid, um
        stabile Kanten-Indizes + ShapeIDs zu persistieren.
        """
        migrated_features = 0

        def _is_same_edge(edge_a, edge_b) -> bool:
            try:
                wa = edge_a.wrapped if hasattr(edge_a, "wrapped") else edge_a
                wb = edge_b.wrapped if hasattr(edge_b, "wrapped") else edge_b
                return wa.IsSame(wb)
            except Exception:
                return edge_a is edge_b

        try:
            from modeling.geometric_selector import GeometricEdgeSelector
            from modeling.tnp_system import ShapeType
        except Exception:
            return 0

        shape_service = getattr(self, "_shape_naming_service", None)

        for body in self.get_all_bodies():
            solid = getattr(body, "_build123d_solid", None)
            if solid is None or not hasattr(solid, "edges"):
                continue

            all_edges = list(solid.edges())
            if not all_edges:
                continue

            for feature in body.features:
                if not isinstance(feature, NSidedPatchFeature):
                    continue

                if feature.edge_indices and feature.edge_shape_ids:
                    continue

                selectors = feature.geometric_selectors or []
                if not selectors:
                    continue

                resolved_edges = []
                for sel_data in selectors:
                    try:
                        geo_sel = (
                            GeometricEdgeSelector.from_dict(sel_data)
                            if isinstance(sel_data, dict)
                            else sel_data
                        )
                        if not hasattr(geo_sel, "find_best_match"):
                            continue
                        edge = geo_sel.find_best_match(all_edges)
                        if edge is None:
                            continue
                        if any(_is_same_edge(edge, existing) for existing in resolved_edges):
                            continue
                        resolved_edges.append(edge)
                    except Exception:
                        continue

                if len(resolved_edges) < 3:
                    continue

                resolved_indices = []
                for edge in resolved_edges:
                    match_idx = None
                    for i, candidate in enumerate(all_edges):
                        if _is_same_edge(candidate, edge):
                            match_idx = i
                            break
                    if match_idx is not None and match_idx not in resolved_indices:
                        resolved_indices.append(match_idx)

                if len(resolved_indices) < 3:
                    continue

                changed = False
                if feature.edge_indices != resolved_indices:
                    feature.edge_indices = resolved_indices
                    changed = True

                try:
                    canonical_selectors = [
                        GeometricEdgeSelector.from_edge(edge).to_dict()
                        for edge in resolved_edges
                    ]
                    if canonical_selectors:
                        feature.geometric_selectors = canonical_selectors
                        changed = True
                except Exception:
                    pass

                if shape_service:
                    migrated_shape_ids = []
                    for local_idx, edge in enumerate(resolved_edges):
                        try:
                            shape_id = shape_service.find_shape_id_by_edge(edge)
                            if shape_id is None and hasattr(edge, "wrapped"):
                                ec = edge.center()
                                edge_len = edge.length if hasattr(edge, "length") else 0.0
                                shape_id = shape_service.register_shape(
                                    ocp_shape=edge.wrapped,
                                    shape_type=ShapeType.EDGE,
                                    feature_id=feature.id,
                                    local_index=local_idx,
                                    geometry_data=(ec.X, ec.Y, ec.Z, edge_len),
                                )
                            if shape_id is not None:
                                migrated_shape_ids.append(shape_id)
                        except Exception:
                            continue

                    if migrated_shape_ids and (
                        not feature.edge_shape_ids or len(feature.edge_shape_ids) != len(migrated_shape_ids)
                    ):
                        feature.edge_shape_ids = migrated_shape_ids
                        changed = True

                if changed:
                    migrated_features += 1
                    body.invalidate_mesh()

        if migrated_features > 0:
            logger.info(
                f"[MIGRATION] NSided Features auf edge_indices/ShapeIDs migriert: {migrated_features}"
            )
        return migrated_features

    def _migrate_loaded_face_refs_to_indices(self) -> int:
        """
        Runtime migration after load:
        fills missing face/path indices from geometric selectors.

        Ziel:
        - Keine shape-id-only Referenzen ohne Index zuruecklassen
        - stabile Index-Referenzen fuer Face/Edge-basierte Features erzeugen
        """
        migrated_features = 0

        try:
            from modeling.geometric_selector import GeometricFaceSelector, GeometricEdgeSelector
            from modeling.topology_indexing import face_index_of, edge_index_of
        except Exception:
            return 0

        def _as_indices(raw_values) -> List[int]:
            valid: List[int] = []
            for raw_idx in list(raw_values or []):
                try:
                    idx = int(raw_idx)
                except Exception:
                    continue
                if idx < 0:
                    continue
                if idx not in valid:
                    valid.append(idx)
            return valid

        def _selector_to_face_index(selector_data: Any, all_faces: List[Any], solid: Any) -> Optional[int]:
            if not selector_data:
                return None
            try:
                if isinstance(selector_data, dict):
                    selector = GeometricFaceSelector.from_dict(selector_data)
                elif hasattr(selector_data, "find_best_match"):
                    selector = selector_data
                else:
                    return None
            except Exception:
                return None

            try:
                face = selector.find_best_match(all_faces)
                if face is None:
                    return None
                idx = face_index_of(solid, face)
                if idx is None:
                    return None
                idx = int(idx)
                if idx < 0:
                    return None
                return idx
            except Exception:
                return None

        def _selector_to_edge_index(selector_data: Any, all_edges: List[Any], solid: Any) -> Optional[int]:
            if not selector_data:
                return None
            try:
                if isinstance(selector_data, dict):
                    selector = GeometricEdgeSelector.from_dict(selector_data)
                elif hasattr(selector_data, "find_best_match"):
                    selector = selector_data
                else:
                    return None
            except Exception:
                return None

            try:
                edge = selector.find_best_match(all_edges)
                if edge is None:
                    return None
                idx = edge_index_of(solid, edge)
                if idx is None:
                    return None
                idx = int(idx)
                if idx < 0:
                    return None
                return idx
            except Exception:
                return None

        for body in self.get_all_bodies():
            solid = getattr(body, "_build123d_solid", None)
            if solid is None:
                continue

            all_faces = list(solid.faces()) if hasattr(solid, "faces") else []
            all_edges = list(solid.edges()) if hasattr(solid, "edges") else []
            face_count = len(all_faces)
            edge_count = len(all_edges)

            if face_count == 0 and edge_count == 0:
                continue

            for feature in body.features:
                changed = False

                def _ensure_face_indices(index_attr: str, selector_attr: str) -> bool:
                    if face_count == 0:
                        return False

                    raw_indices = getattr(feature, index_attr, None)
                    valid_indices = _as_indices(raw_indices)
                    if valid_indices:
                        return False

                    selectors = list(getattr(feature, selector_attr, []) or [])
                    resolved: List[int] = []
                    for sel in selectors:
                        idx = _selector_to_face_index(sel, all_faces, solid)
                        if idx is not None and idx not in resolved:
                            resolved.append(idx)

                    if resolved:
                        setattr(feature, index_attr, resolved)
                        return True
                    return False

                def _ensure_single_face_index(index_attr: str, selector_attr: str) -> bool:
                    if face_count == 0:
                        return False

                    raw_idx = getattr(feature, index_attr, None)
                    if raw_idx is not None:
                        return False

                    selector_data = getattr(feature, selector_attr, None)
                    resolved_idx = _selector_to_face_index(selector_data, all_faces, solid)
                    if resolved_idx is not None:
                        setattr(feature, index_attr, resolved_idx)
                        return True
                    return False

                if isinstance(feature, (HoleFeature, DraftFeature, SurfaceTextureFeature)):
                    changed |= _ensure_face_indices("face_indices", "face_selectors")
                elif isinstance(feature, ShellFeature):
                    changed |= _ensure_face_indices("face_indices", "opening_face_selectors")
                elif isinstance(feature, HollowFeature):
                    changed |= _ensure_face_indices("opening_face_indices", "opening_face_selectors")
                elif isinstance(feature, (ThreadFeature, ExtrudeFeature)):
                    changed |= _ensure_single_face_index("face_index", "face_selector")
                elif isinstance(feature, SweepFeature):
                    # Profile-Face (body-face sweep profile)
                    if face_count > 0:
                        if feature.profile_face_index is None:
                            resolved_profile_idx = _selector_to_face_index(
                                getattr(feature, "profile_geometric_selector", None),
                                all_faces,
                                solid,
                            )
                            if resolved_profile_idx is not None:
                                feature.profile_face_index = resolved_profile_idx
                                changed = True

                    # Path-Edges
                    path_data = feature.path_data if isinstance(feature.path_data, dict) else {}
                    raw_edge_indices = path_data.get("edge_indices", [])
                    valid_edge_indices = _as_indices(raw_edge_indices)

                    if not valid_edge_indices and edge_count > 0:
                        resolved_path_idx = _selector_to_edge_index(
                            getattr(feature, "path_geometric_selector", None),
                            all_edges,
                            solid,
                        )
                        if resolved_path_idx is not None:
                            path_data["edge_indices"] = [resolved_path_idx]
                            feature.path_data = path_data
                            changed = True

                if changed:
                    migrated_features += 1
                    body.invalidate_mesh()

        if migrated_features > 0:
            logger.info(
                f"[MIGRATION] Face/Path Referenzen auf Indizes migriert: {migrated_features}"
            )
        return migrated_features

    def _migrate_loaded_edge_refs_to_shape_ids(self) -> int:
        """
        Runtime migration after load:
        synchronizes edge_shape_ids from stable edge_indices for strict edge features.

        Hintergrund:
        Nach Save/Load kÃ¶nnen gespeicherte edge_shape_ids stale sein, obwohl edge_indices
        weiterhin korrekt auflÃ¶sbar sind. FÃ¼r Fillet/Chamfer sollen shape_ids danach
        auf die aktuell indexaufgelÃ¶sten Kanten zeigen.
        """
        service = getattr(self, "_shape_naming_service", None)
        if service is None:
            return 0

        try:
            from modeling.topology_indexing import edge_from_index
            from modeling.tnp_system import ShapeType
        except Exception:
            return 0

        migrated_features = 0

        def _as_indices(raw_values) -> List[int]:
            valid: List[int] = []
            for raw_idx in list(raw_values or []):
                try:
                    idx = int(raw_idx)
                except Exception:
                    continue
                if idx < 0:
                    continue
                if idx not in valid:
                    valid.append(idx)
            return valid

        for body in self.get_all_bodies():
            solid = getattr(body, "_build123d_solid", None)
            if solid is None:
                continue

            for feature in body.features:
                if not isinstance(feature, (FilletFeature, ChamferFeature)):
                    continue

                edge_indices = _as_indices(getattr(feature, "edge_indices", []))
                if not edge_indices:
                    continue

                new_shape_ids = []
                for local_idx, edge_idx in enumerate(edge_indices):
                    try:
                        edge = edge_from_index(solid, int(edge_idx))
                    except Exception:
                        edge = None
                    if edge is None:
                        continue

                    try:
                        shape_id = service.find_shape_id_by_edge(edge)
                        if shape_id is None and hasattr(edge, "wrapped"):
                            ec = edge.center()
                            edge_len = edge.length if hasattr(edge, "length") else 0.0
                            shape_id = service.register_shape(
                                ocp_shape=edge.wrapped,
                                shape_type=ShapeType.EDGE,
                                feature_id=feature.id,
                                local_index=local_idx,
                                geometry_data=(ec.X, ec.Y, ec.Z, edge_len),
                            )
                        if shape_id is not None:
                            new_shape_ids.append(shape_id)
                    except Exception:
                        continue

                if len(new_shape_ids) != len(edge_indices):
                    continue

                old_ids = list(getattr(feature, "edge_shape_ids", []) or [])
                old_tokens = [sid.uuid for sid in old_ids if hasattr(sid, "uuid")]
                new_tokens = [sid.uuid for sid in new_shape_ids if hasattr(sid, "uuid")]
                if old_tokens != new_tokens:
                    feature.edge_shape_ids = new_shape_ids
                    migrated_features += 1
                    body.invalidate_mesh()

        if migrated_features > 0:
            logger.info(
                f"[MIGRATION] Edge ShapeIDs aus edge_indices synchronisiert: {migrated_features}"
            )
        return migrated_features

    def _migrate_loaded_face_refs_to_shape_ids(self) -> int:
        """
        Runtime migration after load:
        synchronizes face ShapeIDs from stable face indices for metadata-only features.

        Hintergrund:
        Fuer verbrauchende Features (z. B. Hole/Draft/Push-Pull) zeigen face_indices
        auf den VOR-Feature-Zustand. Diese koennen aus dem final geladenen BREP
        nicht sicher rekonstruiert werden. Daher wird hier nur fuer nicht-
        destruktive SurfaceTexture-Referenzen migriert.
        """
        service = getattr(self, "_shape_naming_service", None)
        if service is None:
            return 0

        try:
            from modeling.topology_indexing import face_from_index
            from modeling.tnp_system import ShapeType
        except Exception:
            return 0

        migrated_features = 0

        def _as_indices(raw_values) -> List[int]:
            valid: List[int] = []
            for raw_idx in list(raw_values or []):
                try:
                    idx = int(raw_idx)
                except Exception:
                    continue
                if idx < 0:
                    continue
                if idx not in valid:
                    valid.append(idx)
            return valid

        def _resolve_face_shape_id(feature, solid, face_idx: int, local_idx: int):
            try:
                face = face_from_index(solid, int(face_idx))
            except Exception:
                face = None
            if face is None:
                return None

            try:
                shape_id = service.find_shape_id_by_face(face, require_exact=True)
            except Exception:
                shape_id = None

            local_index = getattr(shape_id, "local_index", None) if shape_id is not None else None
            shape_slot_matches = (
                shape_id is not None
                and getattr(shape_id, "feature_id", None) == feature.id
                and isinstance(local_index, int)
                and local_index == int(local_idx)
            )
            if not shape_slot_matches:
                shape_id = None

            if shape_id is None and hasattr(face, "wrapped"):
                try:
                    fc = face.center()
                    area = float(face.area) if hasattr(face, "area") else 0.0
                    shape_id = service.register_shape(
                        ocp_shape=face.wrapped,
                        shape_type=ShapeType.FACE,
                        feature_id=feature.id,
                        local_index=int(local_idx),
                        geometry_data=(fc.X, fc.Y, fc.Z, area),
                    )
                except Exception:
                    return None
            return shape_id

        def _shape_tokens(shape_values: List[Any]) -> List[str]:
            return [sid.uuid for sid in shape_values if hasattr(sid, "uuid")]

        def _sync_face_list_refs(feature, solid, index_attr: str, shape_attr: str) -> bool:
            index_values = _as_indices(getattr(feature, index_attr, []))
            if not index_values:
                return False

            new_shape_ids = []
            for local_idx, face_idx in enumerate(index_values):
                shape_id = _resolve_face_shape_id(feature, solid, face_idx, local_idx)
                if shape_id is None:
                    return False
                new_shape_ids.append(shape_id)

            changed = False
            old_indices = list(getattr(feature, index_attr, []) or [])
            if old_indices != index_values:
                setattr(feature, index_attr, index_values)
                changed = True

            old_shape_ids = list(getattr(feature, shape_attr, []) or [])
            if _shape_tokens(old_shape_ids) != _shape_tokens(new_shape_ids):
                setattr(feature, shape_attr, new_shape_ids)
                changed = True

            return changed

        for body in self.get_all_bodies():
            solid = getattr(body, "_build123d_solid", None)
            if solid is None:
                continue

            for feature in body.features:
                changed = False
                if isinstance(feature, SurfaceTextureFeature):
                    changed |= _sync_face_list_refs(feature, solid, "face_indices", "face_shape_ids")

                if changed:
                    migrated_features += 1
                    body.invalidate_mesh()

        if migrated_features > 0:
            logger.info(
                f"[MIGRATION] Face ShapeIDs aus face_indices synchronisiert: {migrated_features}"
            )
        return migrated_features

    def _rehydrate_shape_naming_service_from_loaded_bodies(self) -> int:
        """
        Seed ShapeNamingService after load from already vorhandenen topology indices.

        Dadurch koennen bestehende ShapeIDs wieder direkt auf aktuelle Faces/Edges
        zeigen, auch wenn kein kompletter Feature-Rebuild stattgefunden hat.
        """
        service = getattr(self, "_shape_naming_service", None)
        if service is None:
            return 0

        try:
            from modeling.topology_indexing import face_from_index, edge_from_index
        except Exception:
            return 0

        seeded = 0

        def _pick_index(shape_id: Any, position: int, index_values: List[Any]) -> Optional[int]:
            candidates: List[Any] = []
            if position < len(index_values):
                candidates.append(index_values[position])
            local_index = getattr(shape_id, "local_index", None)
            if isinstance(local_index, int) and 0 <= local_index < len(index_values):
                candidates.append(index_values[local_index])
            if len(index_values) == 1:
                candidates.append(index_values[0])

            for raw_idx in candidates:
                try:
                    idx = int(raw_idx)
                except Exception:
                    continue
                if idx >= 0:
                    return idx
            return None

        def _seed_pairs(
            solid: Any,
            shape_ids: List[Any],
            index_values: List[Any],
            resolver,
        ) -> int:
            local_seeded = 0
            for i, shape_id in enumerate(shape_ids):
                if not hasattr(shape_id, "uuid"):
                    continue
                idx = _pick_index(shape_id, i, index_values)
                if idx is None:
                    continue
                try:
                    topo_entity = resolver(solid, idx)
                except Exception:
                    topo_entity = None
                if topo_entity is None or not hasattr(topo_entity, "wrapped"):
                    continue
                try:
                    service.seed_shape(shape_id, topo_entity.wrapped)
                    local_seeded += 1
                except Exception:
                    continue
            return local_seeded

        for body in self.get_all_bodies():
            solid = getattr(body, "_build123d_solid", None)
            if solid is None:
                continue

            for feature in body.features:
                seeded += _seed_pairs(
                    solid,
                    list(getattr(feature, "face_shape_ids", []) or []),
                    list(getattr(feature, "face_indices", []) or []),
                    face_from_index,
                )
                seeded += _seed_pairs(
                    solid,
                    list(getattr(feature, "opening_face_shape_ids", []) or []),
                    list(getattr(feature, "opening_face_indices", []) or []),
                    face_from_index,
                )
                seeded += _seed_pairs(
                    solid,
                    list(getattr(feature, "edge_shape_ids", []) or []),
                    list(getattr(feature, "edge_indices", []) or []),
                    edge_from_index,
                )

                single_face_shape = getattr(feature, "face_shape_id", None)
                single_face_index = getattr(feature, "face_index", None)
                if single_face_shape is not None and single_face_index is not None:
                    seeded += _seed_pairs(
                        solid,
                        [single_face_shape],
                        [single_face_index],
                        face_from_index,
                    )

                if isinstance(feature, SweepFeature):
                    if getattr(feature, "profile_shape_id", None) is not None:
                        seeded += _seed_pairs(
                            solid,
                            [feature.profile_shape_id],
                            [feature.profile_face_index],
                            face_from_index,
                        )

                    if getattr(feature, "path_shape_id", None) is not None:
                        path_data = feature.path_data if isinstance(feature.path_data, dict) else {}
                        path_indices = list(path_data.get("edge_indices", []) or [])
                        seeded += _seed_pairs(
                            solid,
                            [feature.path_shape_id],
                            path_indices,
                            edge_from_index,
                        )

        if seeded > 0:
            logger.info(f"[MIGRATION] ShapeNamingService aus geladenen Indizes rehydriert: {seeded}")
        return seeded

    def save_project(self, filename: str) -> bool:
        """
        Speichert Projekt als MashCAD-Datei (.mshcad).

        Args:
            filename: Ausgabepfad

        Returns:
            True bei Erfolg
        """
        import json
        from pathlib import Path

        try:
            path = Path(filename)
            if not path.suffix:
                path = path.with_suffix(".mshcad")

            data = self.to_dict()

            import numpy as np

            class _ProjectEncoder(json.JSONEncoder):
                """JSON Encoder fÃ¼r Projekt-Daten mit UnterstÃ¼tzung fÃ¼r NumPy und Geometrie-Objekte."""
                def default(self, obj):
                    # NumPy-Typen
                    if isinstance(obj, (np.integer,)):
                        return int(obj)
                    if isinstance(obj, (np.floating,)):
                        return float(obj)
                    if isinstance(obj, np.ndarray):
                        return obj.tolist()
                    # Objekte mit to_dict Methode (Geometrie-Klassen, etc.)
                    if hasattr(obj, 'to_dict'):
                        return obj.to_dict()
                    # Dataclasses als Fallback
                    if hasattr(obj, '__dataclass_fields__'):
                        return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
                    return super().default(obj)

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, cls=_ProjectEncoder)

            return True

        except Exception as e:
            logger.error(f"Projekt konnte nicht gespeichert werden: {e}")
            return False

    @classmethod
    def load_project(cls, filename: str) -> Optional['Document']:
        """
        LÃ¤dt Projekt aus MashCAD-Datei (.mshcad).

        Args:
            filename: Pfad zur Projektdatei

        Returns:
            Document oder None bei Fehler
        """
        import json
        from pathlib import Path

        try:
            path = Path(filename)
            if not path.exists():
                logger.error(f"Projektdatei nicht gefunden: {filename}")
                return None

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            doc = cls.from_dict(data)

            # Bodies: BREP direkt laden oder Rebuild als Fallback
            for body in doc.get_all_bodies():
                if body._build123d_solid is not None:
                    logger.debug(f"Body '{body.name}': BREP direkt geladen (kein Rebuild nÃ¶tig)")
                elif body.features:
                    try:
                        body._rebuild()
                        logger.debug(f"Body '{body.name}': Rebuild aus Feature-Tree")
                    except Exception as e:
                        logger.warning(f"Body '{body.name}' rebuild fehlgeschlagen: {e}")

            # Einmalige Legacy-Migration fÃ¼r NSided edge_selectors -> edge_indices/ShapeIDs.
            migrated_nsided = doc._migrate_loaded_nsided_features_to_indices()
            migrated_face_refs = doc._migrate_loaded_face_refs_to_indices()
            seeded_shape_refs = doc._rehydrate_shape_naming_service_from_loaded_bodies()
            migrated_face_shape_refs = doc._migrate_loaded_face_refs_to_shape_ids()
            migrated_edge_shape_refs = doc._migrate_loaded_edge_refs_to_shape_ids()
            if seeded_shape_refs > 0 and is_enabled("tnp_debug_logging"):
                logger.debug(
                    f"[MIGRATION] ShapeNamingService Rehydration: {seeded_shape_refs} mappings"
                )

            migrated_total = (
                migrated_nsided
                + migrated_face_refs
                + migrated_face_shape_refs
                + migrated_edge_shape_refs
            )
            if migrated_total > 0:
                import shutil

                backup_path = path.with_suffix(path.suffix + ".pre_nsided_migration.bak")
                try:
                    if not backup_path.exists():
                        shutil.copy2(path, backup_path)
                        logger.info(f"[MIGRATION] Backup vor Referenz-Migration erstellt: {backup_path}")
                except Exception as e:
                    logger.warning(f"[MIGRATION] Backup fuer Referenz-Migration fehlgeschlagen: {e}")

                if doc.save_project(str(path)):
                    logger.info(
                        "[MIGRATION] Projektdatei nach Referenz-Migration aktualisiert: "
                        f"{path} (nsided={migrated_nsided}, face_refs={migrated_face_refs}, "
                        f"face_shape_refs={migrated_face_shape_refs}, "
                        f"edge_shape_refs={migrated_edge_shape_refs})"
                    )
                else:
                    logger.warning(
                        "[MIGRATION] Projektdatei konnte nach Referenz-Migration nicht gespeichert werden"
                    )

            return doc

        except json.JSONDecodeError as e:
            logger.error(f"UngÃ¼ltiges JSON in Projektdatei: {e}")
            return None
        except Exception as e:
            logger.error(f"Projekt konnte nicht geladen werden: {e}")
            return None





__all__ = ['Document', 'SplitResult']
