"""
Component - Assembly System Container

Container für Bodies, Sketches, Planes mit eigenem Koordinatensystem.
Ermöglicht hierarchische Strukturen wie in CAD:
- Document → Root Component → Sub-Components
- Jede Component enthält Bodies, Sketches, Planes
- Sub-Components können eigene Objekte enthalten

Phase 1: Datenmodell für Assembly-System
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any
import uuid
from loguru import logger


@dataclass
class Component:
    """
    Container für Bodies, Sketches, Planes mit eigenem Koordinatensystem.

    Ermöglicht hierarchische Strukturen wie in CAD:
    - Document → Root Component → Sub-Components
    - Jede Component enthält Bodies, Sketches, Planes
    - Sub-Components können eigene Objekte enthalten

    Phase 1: Datenmodell für Assembly-System
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Component"

    # Enthaltene Objekte (forward references - werden später resolved)
    bodies: List['Body'] = field(default_factory=list)
    sketches: List['Sketch'] = field(default_factory=list)
    planes: List['ConstructionPlane'] = field(default_factory=list)

    # Hierarchie
    sub_components: List['Component'] = field(default_factory=list)
    parent: Optional['Component'] = field(default=None, repr=False)  # Avoid circular repr

    # Transform relativ zum Parent (für Assembly-Positionierung)
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # Euler XYZ in degrees

    # State
    visible: bool = True
    is_active: bool = False  # Nur eine Component kann aktiv sein
    expanded: bool = True    # UI-State für Tree-View

    def __post_init__(self):
        """Logging für neue Component."""
        logger.debug(f"Component erstellt: {self.name} (id={self.id})")

    # =========================================================================
    # Hierarchie-Navigation
    # =========================================================================

    def get_all_bodies(self, recursive: bool = True) -> List['Body']:
        """
        Gibt alle Bodies dieser Component zurück.

        Args:
            recursive: Wenn True, auch Bodies aus Sub-Components

        Returns:
            Liste aller Bodies
        """
        result = list(self.bodies)
        if recursive:
            for sub in self.sub_components:
                result.extend(sub.get_all_bodies(recursive=True))
        return result

    def get_all_sketches(self, recursive: bool = True) -> List['Sketch']:
        """Gibt alle Sketches dieser Component zurück."""
        result = list(self.sketches)
        if recursive:
            for sub in self.sub_components:
                result.extend(sub.get_all_sketches(recursive=True))
        return result

    def get_all_components(self) -> List['Component']:
        """Gibt alle Sub-Components rekursiv zurück (inkl. dieser)."""
        result = [self]
        for sub in self.sub_components:
            result.extend(sub.get_all_components())
        return result

    def find_component_by_id(self, comp_id: str) -> Optional['Component']:
        """Findet Component nach ID (rekursiv)."""
        if self.id == comp_id:
            return self
        for sub in self.sub_components:
            found = sub.find_component_by_id(comp_id)
            if found:
                return found
        return None

    def find_body_by_id(self, body_id: str) -> Optional['Body']:
        """Findet Body nach ID (rekursiv)."""
        for body in self.bodies:
            if body.id == body_id:
                return body
        for sub in self.sub_components:
            found = sub.find_body_by_id(body_id)
            if found:
                return found
        return None

    def get_root(self) -> 'Component':
        """Gibt die Root-Component zurück."""
        if self.parent is None:
            return self
        return self.parent.get_root()

    def get_path(self) -> List['Component']:
        """Gibt den Pfad von Root zu dieser Component zurück."""
        if self.parent is None:
            return [self]
        return self.parent.get_path() + [self]

    # =========================================================================
    # Component Management
    # =========================================================================

    def add_sub_component(self, name: str = None) -> 'Component':
        """
        Erstellt neue Sub-Component.

        Args:
            name: Name der neuen Component (optional)

        Returns:
            Neue Component
        """
        new_comp = Component(name=name or f"Component{len(self.sub_components)+1}")
        new_comp.parent = self
        self.sub_components.append(new_comp)
        logger.info(f"Sub-Component erstellt: {new_comp.name} in {self.name}")
        return new_comp

    def remove_sub_component(self, comp: 'Component') -> bool:
        """
        Entfernt Sub-Component.

        Args:
            comp: Zu entfernende Component

        Returns:
            True wenn erfolgreich
        """
        if comp in self.sub_components:
            self.sub_components.remove(comp)
            comp.parent = None
            logger.info(f"Sub-Component entfernt: {comp.name} aus {self.name}")
            return True
        return False

    def move_body_to(self, body: 'Body', target: 'Component') -> bool:
        """
        Verschiebt Body in andere Component.

        Args:
            body: Zu verschiebender Body
            target: Ziel-Component

        Returns:
            True wenn erfolgreich
        """
        if body in self.bodies:
            self.bodies.remove(body)
            target.bodies.append(body)
            logger.info(f"Body '{body.name}' verschoben: {self.name} → {target.name}")
            return True
        return False

    # =========================================================================
    # Serialisierung (Phase 2)
    # =========================================================================

    def to_dict(self) -> dict:
        """
        Serialisiert Component zu Dictionary.

        Returns:
            Dictionary für JSON-Serialisierung
        """
        return {
            "id": self.id,
            "name": self.name,
            "position": list(self.position),
            "rotation": list(self.rotation),
            "visible": self.visible,
            "is_active": self.is_active,
            "expanded": self.expanded,
            "bodies": [b.to_dict() for b in self.bodies],
            "sketches": [
                {
                    **s.to_dict(),
                    "plane_origin": list(s.plane_origin) if hasattr(s, 'plane_origin') else [0, 0, 0],
                    "plane_normal": list(s.plane_normal) if hasattr(s, 'plane_normal') else [0, 0, 1],
                    "plane_x_dir": list(s.plane_x_dir) if hasattr(s, 'plane_x_dir') and s.plane_x_dir else None,
                    "plane_y_dir": list(s.plane_y_dir) if hasattr(s, 'plane_y_dir') and s.plane_y_dir else None,
                }
                for s in self.sketches
            ],
            "planes": [
                {
                    "id": p.id,
                    "name": p.name,
                    "origin": list(p.origin),
                    "normal": list(p.normal),
                    "x_dir": list(p.x_dir),
                }
                for p in self.planes
            ],
            "sub_components": [c.to_dict() for c in self.sub_components],
        }

    @classmethod
    def from_dict(cls, data: dict, parent: 'Component' = None) -> 'Component':
        """
        Deserialisiert Component aus Dictionary.

        Args:
            data: Dictionary mit Component-Daten
            parent: Parent-Component (für Hierarchie)

        Returns:
            Neue Component
        """
        # Import here to avoid circular imports
        from modeling.features.base import Feature
        from modeling.construction import ConstructionPlane
        from sketcher import Sketch
        
        comp = cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", "Component"),
            position=tuple(data.get("position", (0.0, 0.0, 0.0))),
            rotation=tuple(data.get("rotation", (0.0, 0.0, 0.0))),
            visible=data.get("visible", True),
            is_active=data.get("is_active", False),
            expanded=data.get("expanded", True),
            parent=parent,
        )

        # Bodies laden - need to import Body lazily
        from modeling.body import Body
        for body_data in data.get("bodies", []):
            try:
                body = Body.from_dict(body_data)
                comp.bodies.append(body)
            except Exception as e:
                logger.warning(f"Body konnte nicht geladen werden: {e}")

        # Sketches laden
        for sketch_data in data.get("sketches", []):
            try:
                sketch = Sketch.from_dict(sketch_data)
                # Plane-Daten wiederherstellen
                if "plane_origin" in sketch_data:
                    sketch.plane_origin = tuple(sketch_data["plane_origin"])
                if "plane_normal" in sketch_data:
                    sketch.plane_normal = tuple(sketch_data["plane_normal"])
                if sketch_data.get("plane_x_dir"):
                    sketch.plane_x_dir = tuple(sketch_data["plane_x_dir"])
                if sketch_data.get("plane_y_dir"):
                    sketch.plane_y_dir = tuple(sketch_data["plane_y_dir"])
                comp.sketches.append(sketch)
            except Exception as e:
                logger.warning(f"Sketch konnte nicht geladen werden: {e}")

        # Planes laden
        for plane_data in data.get("planes", []):
            try:
                plane = ConstructionPlane(
                    id=plane_data.get("id", str(uuid.uuid4())[:8]),
                    name=plane_data.get("name", "Plane"),
                    origin=tuple(plane_data.get("origin", (0, 0, 0))),
                    normal=tuple(plane_data.get("normal", (0, 0, 1))),
                    x_dir=tuple(plane_data.get("x_dir", (1, 0, 0))),
                )
                comp.planes.append(plane)
            except Exception as e:
                logger.warning(f"Plane konnte nicht geladen werden: {e}")

        # Sub-Components rekursiv laden
        for sub_data in data.get("sub_components", []):
            try:
                sub = cls.from_dict(sub_data, parent=comp)
                comp.sub_components.append(sub)
            except Exception as e:
                logger.warning(f"Sub-Component konnte nicht geladen werden: {e}")

        logger.debug(f"Component geladen: {comp.name} ({len(comp.bodies)} Bodies, {len(comp.sketches)} Sketches, {len(comp.sub_components)} Sub-Components)")
        return comp


__all__ = ['Component']
