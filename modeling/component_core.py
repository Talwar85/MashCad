"""
MashCAD - Component Core Module
===============================

AS-001: Component-Core Stabilization for Sprint 3.

Provides the core data structures and management for components in the
assembly system. Components are containers for bodies with their own
coordinate system and transform.

Classes:
 - Component: Dataclass representing a component instance
 - ComponentManager: CRUD operations for components

Usage:
    from modeling.component_core import Component, ComponentManager

    manager = ComponentManager()
    comp = manager.create_component(body=my_body)
    manager.update_component(comp.component_id, name="New Name")
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from loguru import logger


@dataclass
class ComponentTransform:
    """
    Transform data for a component.

    Represents position and orientation in 3D space.
    Position is in world coordinates (x, y, z).
    Rotation is Euler angles in degrees (rx, ry, rz).
    Scale is uniform scale factor (default 1.0).
    """
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # Euler XYZ in degrees
    scale: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize transform to dictionary."""
        return {
            "position": list(self.position),
            "rotation": list(self.rotation),
            "scale": self.scale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ComponentTransform":
        """Create transform from dictionary."""
        return cls(
            position=tuple(data.get("position", [0.0, 0.0, 0.0])),
            rotation=tuple(data.get("rotation", [0.0, 0.0, 0.0])),
            scale=data.get("scale", 1.0),
        )

    def is_identity(self) -> bool:
        """Check if this is an identity transform (no transformation)."""
        return (
            self.position == (0.0, 0.0, 0.0) and
            self.rotation == (0.0, 0.0, 0.0) and
            self.scale == 1.0
        )

    def copy(self) -> "ComponentTransform":
        """Create a copy of this transform."""
        return ComponentTransform(
            position=self.position,
            rotation=self.rotation,
            scale=self.scale,
        )


@dataclass
class Component:
    """
    Component dataclass for AS-001 Component-Core Stabilization.

    A Component is a container for bodies with its own coordinate system.
    It supports hierarchical assembly structures similar to professional CAD systems.

    Attributes:
        component_id: Unique identifier for this component
        name: Human-readable name
        body_reference: Reference to the body this component contains
            (can be body ID or direct reference)
        transform: Position/orientation/scale of this component
        metadata: Additional metadata (custom properties, tags, etc.)

    Example:
        comp = Component(
            name="Wheel Assembly",
            body_reference="body_12345",
            transform=ComponentTransform(position=(10, 0, 0))
        )
    """

    component_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Component"
    body_reference: Optional[str] = None  # Reference to body (ID or name)
    transform: ComponentTransform = field(default_factory=ComponentTransform)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Internal state (not serialized directly)
    _parent: Optional["Component"] = field(default=None, repr=False, compare=False)
    _children: List["Component"] = field(default_factory=list, repr=False, compare=False)
    _body_obj: Any = field(default=None, repr=False, compare=False)  # Direct body reference

    def __post_init__(self):
        """Validate and log component creation."""
        if not self.component_id:
            self.component_id = str(uuid.uuid4())[:8]
        logger.debug(f"[COMPONENT] Created: {self.name} (id={self.component_id})")

    @property
    def parent(self) -> Optional["Component"]:
        """Get parent component."""
        return self._parent

    @parent.setter
    def parent(self, value: Optional["Component"]):
        """Set parent component."""
        if self._parent is not None and value is not None and self._parent != value:
            # Remove from old parent
            if self in self._parent._children:
                self._parent._children.remove(self)
        self._parent = value
        if value is not None and self not in value._children:
            value._children.append(self)

    @property
    def children(self) -> List["Component"]:
        """Get child components (read-only)."""
        return list(self._children)

    def add_child(self, child: "Component") -> None:
        """Add a child component."""
        if child not in self._children:
            child._parent = self
            self._children.append(child)
            logger.debug(f"[COMPONENT] Added child '{child.name}' to '{self.name}'")

    def remove_child(self, child: "Component") -> bool:
        """Remove a child component. Returns True if removed."""
        if child in self._children:
            child._parent = None
            self._children.remove(child)
            logger.debug(f"[COMPONENT] Removed child '{child.name}' from '{self.name}'")
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize component to dictionary for persistence."""
        return {
            "component_id": self.component_id,
            "name": self.name,
            "body_reference": self.body_reference,
            "transform": self.transform.to_dict(),
            "metadata": self.metadata,
            "children": [c.to_dict() for c in self._children],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Component":
        """Create component from dictionary."""
        transform_data = data.get("transform", {})
        transform = ComponentTransform.from_dict(transform_data)

        comp = cls(
            component_id=data.get("component_id", ""),
            name=data.get("name", "Component"),
            body_reference=data.get("body_reference"),
            transform=transform,
            metadata=data.get("metadata", {}),
        )

        # Recursively create children
        for child_data in data.get("children", []):
            child = cls.from_dict(child_data)
            comp.add_child(child)

        return comp

    def get_all_descendants(self) -> List["Component"]:
        """Get all descendant components (children, grandchildren, etc.)."""
        result = list(self._children)
        for child in self._children:
            result.extend(child.get_all_descendants())
        return result

    def find_by_id(self, component_id: str) -> Optional["Component"]:
        """Find a component by ID in this component's subtree."""
        if self.component_id == component_id:
            return self
        for child in self._children:
            found = child.find_by_id(component_id)
            if found:
                return found
        return None

    def get_depth(self) -> int:
        """Get the depth of this component in the hierarchy (root = 0)."""
        depth = 0
        current = self._parent
        while current is not None:
            depth += 1
            current = current._parent
        return depth

    def get_path(self) -> str:
        """Get the path from root to this component."""
        parts = [self.name]
        current = self._parent
        while current is not None:
            parts.append(current.name)
            current = current._parent
        return " / ".join(reversed(parts))


class ComponentManager:
    """
    Manager for CRUD operations on components.

    Provides a centralized way to create, read, update, and delete
    components. Maintains a registry of all components by ID.

    Example:
        manager = ComponentManager()

        # Create a component from a body
        comp = manager.create_component(body=my_body, name="Part1")

        # Get component by ID
        comp = manager.get_component("abc123")

        # Update component
        manager.update_component("abc123", name="Renamed Part")

        # Delete component
        manager.delete_component("abc123")
    """

    def __init__(self):
        """Initialize the component manager."""
        self._components: Dict[str, Component] = {}
        self._root_components: List[Component] = []
        logger.debug("[COMPONENT_MGR] Initialized")

    def create_component(
        self,
        body: Optional[Any] = None,
        name: Optional[str] = None,
        body_reference: Optional[str] = None,
        transform: Optional[ComponentTransform] = None,
        metadata: Optional[Dict[str, Any]] = None,
        parent: Optional[Component] = None,
    ) -> Component:
        """
        Create a new component.

        Args:
            body: Body object to reference (extracts ID automatically)
            name: Component name (defaults to "Component")
            body_reference: Explicit body reference string (overrides body.ID)
            transform: Initial transform (defaults to identity)
            metadata: Additional metadata dictionary
            parent: Parent component (if None, becomes root component)

        Returns:
            The newly created Component

        Raises:
            ValueError: If body_reference is provided but empty
        """
        # Determine body reference
        actual_body_ref = body_reference
        if body is not None and actual_body_ref is None:
            if hasattr(body, 'id'):
                actual_body_ref = body.id
            elif hasattr(body, 'name'):
                actual_body_ref = body.name
            else:
                actual_body_ref = str(id(body))

        # Create component
        comp = Component(
            name=name or "Component",
            body_reference=actual_body_ref,
            transform=transform or ComponentTransform(),
            metadata=metadata or {},
        )
        comp._body_obj = body

        # Register component
        self._components[comp.component_id] = comp

        # Add to hierarchy
        if parent is not None:
            parent.add_child(comp)
        else:
            self._root_components.append(comp)

        logger.info(f"[COMPONENT_MGR] Created component '{comp.name}' (id={comp.component_id})")
        return comp

    def get_component(self, component_id: str) -> Optional[Component]:
        """
        Get a component by ID.

        Args:
            component_id: The component's unique identifier

        Returns:
            The Component if found, None otherwise
        """
        return self._components.get(component_id)

    def update_component(self, component_id: str, **kwargs) -> bool:
        """
        Update a component's properties.

        Args:
            component_id: The component's unique identifier
            **kwargs: Properties to update (name, body_reference, transform, metadata)

        Returns:
            True if update was successful, False if component not found

        Example:
            manager.update_component("abc123", name="New Name")
            manager.update_component("abc123", transform=ComponentTransform(position=(10, 0, 0)))
        """
        comp = self._components.get(component_id)
        if comp is None:
            logger.warning(f"[COMPONENT_MGR] Component not found: {component_id}")
            return False

        # Update allowed properties
        if 'name' in kwargs:
            comp.name = kwargs['name']
        if 'body_reference' in kwargs:
            comp.body_reference = kwargs['body_reference']
        if 'transform' in kwargs:
            comp.transform = kwargs['transform']
        if 'metadata' in kwargs:
            comp.metadata = kwargs['metadata']
        if 'body' in kwargs:
            body = kwargs['body']
            comp._body_obj = body
            if hasattr(body, 'id'):
                comp.body_reference = body.id

        logger.debug(f"[COMPONENT_MGR] Updated component '{comp.name}' (id={component_id})")
        return True

    def delete_component(self, component_id: str, recursive: bool = False) -> bool:
        """
        Delete a component.

        Args:
            component_id: The component's unique identifier
            recursive: If True, also delete all child components

        Returns:
            True if deletion was successful, False if component not found

        Note:
            Deleting a component does NOT delete the associated body.
            The body remains in the document.
        """
        comp = self._components.get(component_id)
        if comp is None:
            logger.warning(f"[COMPONENT_MGR] Component not found for deletion: {component_id}")
            return False

        # Handle children
        if comp._children:
            if recursive:
                # Recursively delete children
                for child in list(comp._children):
                    self.delete_component(child.component_id, recursive=True)
            else:
                # Remove children from this parent, make them root components
                for child in list(comp._children):
                    child._parent = None
                    self._root_components.append(child)
                comp._children.clear()

        # Remove from parent
        if comp._parent is not None:
            comp._parent.remove_child(comp)

        # Remove from root list if applicable
        if comp in self._root_components:
            self._root_components.remove(comp)

        # Remove from registry
        del self._components[component_id]

        logger.info(f"[COMPONENT_MGR] Deleted component '{comp.name}' (id={component_id})")
        return True

    def list_components(self) -> List[Component]:
        """
        List all registered components.

        Returns:
            List of all Component objects
        """
        return list(self._components.values())

    def list_root_components(self) -> List[Component]:
        """
        List all root components (components without parents).

        Returns:
            List of root Component objects
        """
        return list(self._root_components)

    def get_component_count(self) -> int:
        """Get the total number of registered components."""
        return len(self._components)

    def clear(self) -> None:
        """Clear all components from the manager."""
        self._components.clear()
        self._root_components.clear()
        logger.debug("[COMPONENT_MGR] Cleared all components")

    def find_by_name(self, name: str) -> List[Component]:
        """
        Find components by name.

        Args:
            name: The name to search for

        Returns:
            List of components with matching name
        """
        return [c for c in self._components.values() if c.name == name]

    def find_by_body_reference(self, body_ref: str) -> Optional[Component]:
        """
        Find component by body reference.

        Args:
            body_ref: The body reference to search for

        Returns:
            The first component with matching body reference, or None
        """
        for comp in self._components.values():
            if comp.body_reference == body_ref:
                return comp
        return None

    def get_component_body(self, component_id: str) -> Optional[Any]:
        """
        Get the body object associated with a component.

        Args:
            component_id: The component's unique identifier

        Returns:
            The body object if available, None otherwise
        """
        comp = self._components.get(component_id)
        if comp is None:
            return None
        return comp._body_obj

    def move_component(
        self,
        component_id: str,
        new_parent: Optional[Component]
    ) -> bool:
        """
        Move a component to a new parent.

        Args:
            component_id: The component to move
            new_parent: The new parent component (None for root)

        Returns:
            True if successful, False otherwise
        """
        comp = self._components.get(component_id)
        if comp is None:
            return False

        # Remove from current location
        if comp._parent is not None:
            comp._parent.remove_child(comp)
        if comp in self._root_components:
            self._root_components.remove(comp)

        # Add to new location
        if new_parent is not None:
            new_parent.add_child(comp)
        else:
            comp._parent = None
            self._root_components.append(comp)

        logger.debug(f"[COMPONENT_MGR] Moved component '{comp.name}' to parent '{new_parent.name if new_parent else 'ROOT'}'")
        return True

    def serialize(self) -> Dict[str, Any]:
        """Serialize all components to dictionary."""
        return {
            "components": [c.to_dict() for c in self._root_components],
            "count": len(self._components),
        }

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> "ComponentManager":
        """Create manager from serialized data."""
        manager = cls()
        for comp_data in data.get("components", []):
            comp = Component.from_dict(comp_data)
            manager._components[comp.component_id] = comp
            manager._root_components.append(comp)
            # Register all descendants
            for descendant in comp.get_all_descendants():
                manager._components[descendant.component_id] = descendant
        return manager


# Module-level convenience functions
_default_manager: Optional[ComponentManager] = None


def get_default_manager() -> ComponentManager:
    """Get or create the default component manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = ComponentManager()
    return _default_manager


def reset_default_manager() -> None:
    """Reset the default component manager."""
    global _default_manager
    _default_manager = None
