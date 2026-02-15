"""
MashCad - Viewport Module
3D Viewport mit PyVista
"""

from .extrude_mixin import ExtrudeMixin
from .picking_mixin import PickingMixin
from .body_mixin import BodyRenderingMixin
from .stl_feature_mixin import STLFeatureMixin
from .render_queue import RenderQueue, request_render

# V3: Full Feature (Move/Rotate/Scale/Copy/Mirror) - AKTIV
from .transform_mixin_v3 import TransformMixinV3
from .transform_gizmo_v3 import FullTransformGizmo, FullTransformController, TransformMode

# Aliases für Kompatibilität
TransformMixin = TransformMixinV3
TransformGizmo = FullTransformGizmo
TransformController = FullTransformController

__all__ = [
    'ExtrudeMixin', 'PickingMixin', 'BodyRenderingMixin',
    'STLFeatureMixin',
    'TransformMixin', 'TransformGizmo', 'TransformController',
    'TransformMixinV3', 'FullTransformGizmo', 'FullTransformController', 'TransformMode'
]
