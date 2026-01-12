"""
MashCad - Viewport Module
3D Viewport mit PyVista
"""

from .extrude_mixin import ExtrudeMixin
from .picking_mixin import PickingMixin
from .body_mixin import BodyRenderingMixin
from .transform_mixin import TransformMixin
from .transform_gizmo import TransformGizmo, GizmoMode, GizmoAxis
from .transform_controller import TransformController

# V2: Onshape-Style (aktuell aktiv)
from .transform_mixin_v2 import TransformMixinV2
from .transform_gizmo_v2 import SimpleTransformGizmo, SimpleTransformController

# V3: Full Feature (Move/Rotate/Scale/Copy/Mirror)
from .transform_mixin_v3 import TransformMixinV3
from .transform_gizmo_v3 import FullTransformGizmo, FullTransformController, TransformMode

__all__ = [
    'ExtrudeMixin', 'PickingMixin', 'BodyRenderingMixin', 'TransformMixin',
    'TransformGizmo', 'GizmoMode', 'GizmoAxis', 'TransformController',
    'TransformMixinV2', 'SimpleTransformGizmo', 'SimpleTransformController',
    'TransformMixinV3', 'FullTransformGizmo', 'FullTransformController', 'TransformMode'
]
