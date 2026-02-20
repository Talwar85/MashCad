"""
MashCAD - Component Transform Module
====================================

AS-001: Component-Core Stabilization for Sprint 3.

Provides transform operations for components including position,
rotation, and scale transformations. Integrates with OCP for
actual geometry transformations.

Classes:
    - ComponentTransform: Already defined in component_core.py
    - TransformOperations: Utility class for transform operations

Functions:
    - apply_transform(component, transform): Apply a transform to a component
    - reset_transform(component): Reset component to identity transform
    - combine_transforms(t1, t2): Combine two transforms
    - transform_to_ocp(transform): Convert to OCP gp_Trsf

Usage:
    from modeling.component_transform import apply_transform, reset_transform
    from modeling.component_core import ComponentTransform

    # Apply a translation
    new_transform = ComponentTransform(position=(10, 20, 30))
    apply_transform(component, new_transform)

    # Reset to origin
    reset_transform(component)
"""

from __future__ import annotations

import math
from typing import Tuple, Optional, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from modeling.component_core import Component, ComponentTransform

# OCP imports with fallback
try:
    from OCP.gp import gp_Trsf, gp_Vec, gp_Ax1, gp_Pnt, gp_Dir, gp_Quaternion
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("[COMPONENT_TRANSFORM] OCP not available - transform operations limited")


def apply_transform(
    component: "Component",
    transform: "ComponentTransform",
    accumulate: bool = False
) -> bool:
    """
    Apply a transform to a component.

    Args:
        component: The component to transform
        transform: The transform to apply
        accumulate: If True, add to existing transform; if False, replace

    Returns:
        True if successful, False otherwise

    Example:
        from modeling.component_core import ComponentTransform

        # Move component to new position
        t = ComponentTransform(position=(10, 0, 0))
        apply_transform(my_component, t)

        # Rotate component
        t = ComponentTransform(rotation=(0, 45, 0))  # 45 degrees around Y
        apply_transform(my_component, t)
    """
    if component is None:
        logger.error("[COMPONENT_TRANSFORM] Cannot apply transform to None component")
        return False

    old_transform = component.transform.copy()

    if accumulate:
        # Combine transforms
        new_transform = combine_transforms(old_transform, transform)
    else:
        new_transform = transform.copy()

    component.transform = new_transform

    logger.debug(
        f"[COMPONENT_TRANSFORM] Applied transform to '{component.name}': "
        f"pos={new_transform.position}, rot={new_transform.rotation}"
    )
    return True


def reset_transform(component: "Component") -> bool:
    """
    Reset a component's transform to identity (origin, no rotation, scale 1).

    Args:
        component: The component to reset

    Returns:
        True if successful, False otherwise
    """
    if component is None:
        logger.error("[COMPONENT_TRANSFORM] Cannot reset transform of None component")
        return False

    from modeling.component_core import ComponentTransform

    component.transform = ComponentTransform()
    logger.debug(f"[COMPONENT_TRANSFORM] Reset transform for '{component.name}'")
    return True


def combine_transforms(
    t1: "ComponentTransform",
    t2: "ComponentTransform"
) -> "ComponentTransform":
    """
    Combine two transforms (t1 then t2).

    The resulting transform represents applying t1 first, then t2.

    Args:
        t1: First transform
        t2: Second transform

    Returns:
        Combined transform
    """
    from modeling.component_core import ComponentTransform

    # Combine positions (add)
    new_position = (
        t1.position[0] + t2.position[0],
        t1.position[1] + t2.position[1],
        t1.position[2] + t2.position[2],
    )

    # Combine rotations (add Euler angles - simplified, not true rotation composition)
    # For accurate rotation composition, use quaternion math
    new_rotation = (
        t1.rotation[0] + t2.rotation[0],
        t1.rotation[1] + t2.rotation[1],
        t1.rotation[2] + t2.rotation[2],
    )

    # Combine scales (multiply)
    new_scale = t1.scale * t2.scale

    return ComponentTransform(
        position=new_position,
        rotation=new_rotation,
        scale=new_scale,
    )


def transform_to_ocp(transform: "ComponentTransform"):
    """
    Convert a ComponentTransform to an OCP gp_Trsf object.

    Args:
        transform: The transform to convert

    Returns:
        gp_Trsf object if OCP is available, None otherwise
    """
    if not HAS_OCP:
        logger.warning("[COMPONENT_TRANSFORM] OCP not available for transform conversion")
        return None

    trsf = gp_Trsf()

    # Apply translation
    pos = transform.position
    if pos != (0.0, 0.0, 0.0):
        vec = gp_Vec(pos[0], pos[1], pos[2])
        trsf.SetTranslation(vec)

    # Apply rotation (Euler angles in degrees)
    rot = transform.rotation
    if rot != (0.0, 0.0, 0.0):
        # Apply rotations in XYZ order
        if rot[0] != 0:
            angle_rad = math.radians(rot[0])
            axis = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0))
            rot_x = gp_Trsf()
            rot_x.SetRotation(axis, angle_rad)
            trsf = trsf.Multiplied(rot_x)

        if rot[1] != 0:
            angle_rad = math.radians(rot[1])
            axis = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0))
            rot_y = gp_Trsf()
            rot_y.SetRotation(axis, angle_rad)
            trsf = trsf.Multiplied(rot_y)

        if rot[2] != 0:
            angle_rad = math.radians(rot[2])
            axis = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
            rot_z = gp_Trsf()
            rot_z.SetRotation(axis, angle_rad)
            trsf = trsf.Multiplied(rot_z)

    # Apply scale
    if transform.scale != 1.0:
        scale_trsf = gp_Trsf()
        scale_trsf.SetScale(gp_Pnt(0, 0, 0), transform.scale)
        trsf = trsf.Multiplied(scale_trsf)

    return trsf


def apply_transform_to_shape(shape, transform: "ComponentTransform"):
    """
    Apply a transform to an OCP shape.

    Args:
        shape: The OCP shape (TopoDS_Shape) to transform
        transform: The transform to apply

    Returns:
        The transformed shape, or original if transformation failed
    """
    if not HAS_OCP:
        logger.warning("[COMPONENT_TRANSFORM] OCP not available for shape transformation")
        return shape

    trsf = transform_to_ocp(transform)
    if trsf is None:
        return shape

    try:
        builder = BRepBuilderAPI_Transform(shape, trsf, True)  # Copy shape
        builder.Build()
        if builder.IsDone():
            return builder.Shape()
        else:
            logger.error("[COMPONENT_TRANSFORM] Transform operation failed")
            return shape
    except Exception as e:
        logger.error(f"[COMPONENT_TRANSFORM] Transform error: {e}")
        return shape


def get_world_transform(component: "Component") -> "ComponentTransform":
    """
    Calculate the world transform of a component by accumulating
    all parent transforms.

    Args:
        component: The component to get world transform for

    Returns:
        The accumulated world transform
    """
    from modeling.component_core import ComponentTransform

    if component is None:
        return ComponentTransform()

    # Start with this component's transform
    result = component.transform.copy()

    # Accumulate parent transforms
    current = component.parent
    while current is not None:
        result = combine_transforms(current.transform, result)
        current = current.parent

    return result


def set_position(
    component: "Component",
    position: Tuple[float, float, float]
) -> bool:
    """
    Set the position of a component.

    Args:
        component: The component to modify
        position: New position (x, y, z)

    Returns:
        True if successful
    """
    if component is None:
        return False

    component.transform = component.transform.__class__(
        position=position,
        rotation=component.transform.rotation,
        scale=component.transform.scale,
    )
    logger.debug(f"[COMPONENT_TRANSFORM] Set position of '{component.name}' to {position}")
    return True


def set_rotation(
    component: "Component",
    rotation: Tuple[float, float, float]
) -> bool:
    """
    Set the rotation of a component.

    Args:
        component: The component to modify
        rotation: New rotation (rx, ry, rz) in degrees

    Returns:
        True if successful
    """
    if component is None:
        return False

    component.transform = component.transform.__class__(
        position=component.transform.position,
        rotation=rotation,
        scale=component.transform.scale,
    )
    logger.debug(f"[COMPONENT_TRANSFORM] Set rotation of '{component.name}' to {rotation}")
    return True


def set_scale(component: "Component", scale: float) -> bool:
    """
    Set the uniform scale of a component.

    Args:
        component: The component to modify
        scale: New scale factor (1.0 = original size)

    Returns:
        True if successful
    """
    if component is None:
        return False

    component.transform = component.transform.__class__(
        position=component.transform.position,
        rotation=component.transform.rotation,
        scale=scale,
    )
    logger.debug(f"[COMPONENT_TRANSFORM] Set scale of '{component.name}' to {scale}")
    return True


def translate(
    component: "Component",
    offset: Tuple[float, float, float]
) -> bool:
    """
    Translate a component by an offset.

    Args:
        component: The component to translate
        offset: Translation offset (dx, dy, dz)

    Returns:
        True if successful
    """
    if component is None:
        return False

    new_pos = (
        component.transform.position[0] + offset[0],
        component.transform.position[1] + offset[1],
        component.transform.position[2] + offset[2],
    )
    return set_position(component, new_pos)


def rotate(
    component: "Component",
    angles: Tuple[float, float, float]
) -> bool:
    """
    Rotate a component by Euler angles (additive).

    Args:
        component: The component to rotate
        angles: Rotation angles (rx, ry, rz) in degrees

    Returns:
        True if successful
    """
    if component is None:
        return False

    new_rot = (
        component.transform.rotation[0] + angles[0],
        component.transform.rotation[1] + angles[1],
        component.transform.rotation[2] + angles[2],
    )
    return set_rotation(component, new_rot)


def look_at(
    component: "Component",
    target: Tuple[float, float, float],
    up: Tuple[float, float, float] = (0, 0, 1)
) -> bool:
    """
    Orient a component to look at a target point.

    Args:
        component: The component to orient
        target: Target point to look at (x, y, z)
        up: Up vector (default Z-up)

    Returns:
        True if successful
    """
    if not HAS_OCP:
        logger.warning("[COMPONENT_TRANSFORM] OCP required for look_at operation")
        return False

    if component is None:
        return False

    # Calculate direction
    pos = component.transform.position
    dx = target[0] - pos[0]
    dy = target[1] - pos[1]
    dz = target[2] - pos[2]

    # Calculate Euler angles from direction
    # This is a simplified implementation
    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    if length < 1e-10:
        return False

    # Normalize direction
    dx /= length
    dy /= length
    dz /= length

    # Calculate rotation angles (simplified)
    # For accurate orientation, use quaternion-based approach
    ry = math.degrees(math.atan2(dx, dz))
    rx = math.degrees(math.atan2(-dy, math.sqrt(dx*dx + dz*dz)))

    return set_rotation(component, (rx, ry, 0))


class TransformOperations:
    """
    Utility class providing common transform operations.

    This class groups related transform operations and can be
    used as a mixin or utility provider.

    Example:
        ops = TransformOperations()
        ops.move_to(component, (10, 0, 0))
        ops.rotate_by(component, (0, 45, 0))
    """

    @staticmethod
    def move_to(
        component: "Component",
        position: Tuple[float, float, float]
    ) -> bool:
        """Move component to absolute position."""
        return set_position(component, position)

    @staticmethod
    def move_by(
        component: "Component",
        offset: Tuple[float, float, float]
    ) -> bool:
        """Move component by offset."""
        return translate(component, offset)

    @staticmethod
    def rotate_to(
        component: "Component",
        rotation: Tuple[float, float, float]
    ) -> bool:
        """Set absolute rotation."""
        return set_rotation(component, rotation)

    @staticmethod
    def rotate_by(
        component: "Component",
        angles: Tuple[float, float, float]
    ) -> bool:
        """Add rotation to current rotation."""
        return rotate(component, angles)

    @staticmethod
    def scale_to(component: "Component", scale: float) -> bool:
        """Set absolute scale."""
        return set_scale(component, scale)

    @staticmethod
    def reset(component: "Component") -> bool:
        """Reset transform to identity."""
        return reset_transform(component)

    @staticmethod
    def get_world_position(component: "Component") -> Tuple[float, float, float]:
        """Get world position accounting for parent transforms."""
        world = get_world_transform(component)
        return world.position

    @staticmethod
    def get_world_rotation(component: "Component") -> Tuple[float, float, float]:
        """Get world rotation accounting for parent transforms."""
        world = get_world_transform(component)
        return world.rotation
