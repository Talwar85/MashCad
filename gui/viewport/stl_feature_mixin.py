"""
STL Feature Visualization Mixin for Viewport.

Colorizes detected features in the 3D viewport based on confidence scores.
No library modifications - uses standard PyVista/plotting functions.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FeatureColorScheme:
    """Color scheme for feature visualization."""
    # Base colors (RGB 0-255)
    base_plane_high: Tuple[int, int, int] = (0, 255, 0)      # Green
    base_plane_medium: Tuple[int, int, int] = (100, 255, 100)
    
    hole_high: Tuple[int, int, int] = (0, 100, 255)        # Blue
    hole_medium: Tuple[int, int, int] = (100, 150, 255)
    hole_low: Tuple[int, int, int] = (150, 200, 255)
    
    pocket_high: Tuple[int, int, int] = (255, 255, 0)      # Yellow
    pocket_medium: Tuple[int, int, int] = (255, 200, 100)
    
    fillet_high: Tuple[int, int, int] = (255, 105, 180)    # Pink
    fillet_medium: Tuple[int, int, int] = (255, 150, 200)
    
    uncertain: Tuple[int, int, int] = (255, 165, 0)        # Orange
    
    # Opacity
    opacity_high: float = 1.0
    opacity_medium: float = 0.8
    opacity_low: float = 0.6


class STLFeatureMixin:
    """
    Mixin for STL Feature Visualization in Viewport.
    
    Provides:
    - Face highlighting by feature type and confidence
    - Hover effects
    - Feature selection
    - Color legend
    
    No external library modifications.
    """
    
    # Confidence thresholds
    HIGH_CONFIDENCE = 0.9
    MEDIUM_CONFIDENCE = 0.7
    LOW_CONFIDENCE = 0.5
    
    def __init__(self):
        """Initialize mixin."""
        self._feature_analysis = None
        self._feature_mesh = None
        self._original_mesh = None
        self._feature_actors = {}
        self._color_scheme = FeatureColorScheme()
        self._selected_feature_idx = None
        self._hover_callback = None
        self._selection_callback = None
        self._is_feature_mode_active = False
        
        # Feature type visibility
        self._visible_feature_types = {
            "base_plane": True,
            "hole": True,
            "pocket": True,
            "fillet": True,
        }
    
    def start_feature_analysis_mode(self, mesh_path: str, 
                                    analysis=None,
                                    analysis_callback: Optional[Callable] = None):
        """
        Start feature analysis visualization mode.
        
        Args:
            mesh_path: Path to STL file
            analysis: Optional pre-computed STLFeatureAnalysis
            analysis_callback: Callback to run analysis if not provided
        """
        try:
            import pyvista as pv
            
            # Load mesh
            logger.info(f"Loading mesh for feature analysis: {mesh_path}")
            self._original_mesh = pv.read(mesh_path)
            
            if self._original_mesh is None:
                logger.error("Failed to load mesh")
                return False
            
            # Run analysis if not provided
            if analysis is None and analysis_callback:
                analysis = analysis_callback(mesh_path)
            
            if analysis is None:
                logger.error("No analysis provided or generated")
                return False
            
            self._feature_analysis = analysis
            
            # Create colored mesh
            self._create_feature_visualization()
            
            self._is_feature_mode_active = True
            logger.info("Feature analysis mode started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start feature analysis mode: {e}")
            return False
    
    def stop_feature_analysis_mode(self):
        """Stop feature analysis mode and cleanup."""
        self._clear_feature_actors()
        self._feature_analysis = None
        self._feature_mesh = None
        self._original_mesh = None
        self._selected_feature_idx = None
        self._is_feature_mode_active = False
        logger.info("Feature analysis mode stopped")
    
    def _create_feature_visualization(self):
        """Create colored mesh visualization based on features."""
        try:
            import pyvista as pv
            
            if self._original_mesh is None or self._feature_analysis is None:
                return
            
            # Start with original mesh
            mesh = self._original_mesh.copy()
            
            # Initialize colors (gray for unclassified)
            n_faces = mesh.n_cells
            colors = np.full((n_faces, 3), 200, dtype=np.uint8)  # Light gray
            opacities = np.full(n_faces, 0.3, dtype=np.float32)  # Low opacity
            
            # Color base plane
            if (self._feature_analysis.base_plane and 
                self._visible_feature_types["base_plane"]):
                self._color_base_plane(
                    colors, opacities, 
                    self._feature_analysis.base_plane
                )
            
            # Color holes
            if self._visible_feature_types["hole"]:
                for hole in self._feature_analysis.holes:
                    self._color_hole(colors, opacities, hole)
            
            # Color pockets
            if self._visible_feature_types["pocket"]:
                for pocket in self._feature_analysis.pockets:
                    self._color_pocket(colors, opacities, pocket)
            
            # Store colored mesh
            mesh.cell_data["feature_colors"] = colors
            mesh.cell_data["feature_opacities"] = opacities
            self._feature_mesh = mesh
            
            logger.debug(f"Created feature visualization: {n_faces} faces colored")
            
        except Exception as e:
            logger.error(f"Failed to create feature visualization: {e}")
    
    def _color_base_plane(self, colors: np.ndarray, opacities: np.ndarray,
                          base_plane):
        """Color faces belonging to base plane."""
        try:
            scheme = self._color_scheme
            
            # Determine color based on confidence
            if base_plane.confidence >= self.HIGH_CONFIDENCE:
                color = scheme.base_plane_high
                opacity = scheme.opacity_high
            elif base_plane.confidence >= self.MEDIUM_CONFIDENCE:
                color = scheme.base_plane_medium
                opacity = scheme.opacity_medium
            else:
                color = scheme.uncertain
                opacity = scheme.opacity_low
            
            # Apply to face indices
            for idx in base_plane.face_indices:
                if 0 <= idx < len(colors):
                    colors[idx] = color
                    opacities[idx] = opacity
                    
        except Exception as e:
            logger.debug(f"Failed to color base plane: {e}")
    
    def _color_hole(self, colors: np.ndarray, opacities: np.ndarray, hole):
        """Color faces belonging to a hole."""
        try:
            scheme = self._color_scheme
            
            # Determine color based on confidence
            if hole.confidence >= self.HIGH_CONFIDENCE:
                color = scheme.hole_high
                opacity = scheme.opacity_high
            elif hole.confidence >= self.MEDIUM_CONFIDENCE:
                color = scheme.hole_medium
                opacity = scheme.opacity_medium
            elif hole.confidence >= self.LOW_CONFIDENCE:
                color = scheme.hole_low
                opacity = scheme.opacity_low
            else:
                color = scheme.uncertain
                opacity = scheme.opacity_low
            
            # Apply to face indices
            for idx in hole.face_indices:
                if 0 <= idx < len(colors):
                    colors[idx] = color
                    opacities[idx] = opacity
                    
        except Exception as e:
            logger.debug(f"Failed to color hole: {e}")
    
    def _color_pocket(self, colors: np.ndarray, opacities: np.ndarray, pocket):
        """Color faces belonging to a pocket."""
        try:
            scheme = self._color_scheme
            
            # Determine color based on confidence
            if pocket.confidence >= self.HIGH_CONFIDENCE:
                color = scheme.pocket_high
                opacity = scheme.opacity_high
            else:
                color = scheme.pocket_medium
                opacity = scheme.opacity_medium
            
            # Apply to boundary and bottom faces
            all_faces = (pocket.boundary_face_indices + 
                        pocket.bottom_face_indices)
            
            for idx in all_faces:
                if 0 <= idx < len(colors):
                    colors[idx] = color
                    opacities[idx] = opacity
                    
        except Exception as e:
            logger.debug(f"Failed to color pocket: {e}")
    
    def highlight_feature(self, feature_idx: int, feature_type: str = "hole"):
        """
        Highlight a specific feature in the viewport.
        
        Args:
            feature_idx: Index of feature in its type list
            feature_type: Type of feature ("hole", "pocket", etc.)
        """
        if not self._is_feature_mode_active:
            logger.warning("Feature mode not active")
            return
        
        try:
            # Get feature
            feature = self._get_feature_by_index(feature_idx, feature_type)
            if feature is None:
                logger.warning(f"Feature not found: {feature_type} #{feature_idx}")
                return
            
            self._selected_feature_idx = (feature_idx, feature_type)
            
            # Create highlight visualization
            # (This would typically involve creating a separate actor
            # or modifying the mesh colors more prominently)
            logger.info(f"Highlighted {feature_type} #{feature_idx}")
            
            # Call selection callback if set
            if self._selection_callback:
                self._selection_callback(feature_idx, feature_type, feature)
                
        except Exception as e:
            logger.error(f"Failed to highlight feature: {e}")
    
    def _get_feature_by_index(self, idx: int, feature_type: str):
        """Get feature by index and type."""
        if self._feature_analysis is None:
            return None
        
        if feature_type == "base_plane":
            return self._feature_analysis.base_plane
        elif feature_type == "hole":
            if 0 <= idx < len(self._feature_analysis.holes):
                return self._feature_analysis.holes[idx]
        elif feature_type == "pocket":
            if 0 <= idx < len(self._feature_analysis.pockets):
                return self._feature_analysis.pockets[idx]
        elif feature_type == "fillet":
            if 0 <= idx < len(self._feature_analysis.fillets):
                return self._feature_analysis.fillets[idx]
        
        return None
    
    def set_feature_type_visibility(self, feature_type: str, visible: bool):
        """
        Toggle visibility of a feature type.
        
        Args:
            feature_type: "base_plane", "hole", "pocket", "fillet"
            visible: True to show, False to hide
        """
        if feature_type in self._visible_feature_types:
            self._visible_feature_types[feature_type] = visible
            # Recreate visualization
            self._create_feature_visualization()
            logger.debug(f"Set {feature_type} visibility: {visible}")
    
    def get_feature_info_at_point(self, point: Tuple[float, float, float]) -> Optional[Dict]:
        """
        Get feature information at a 3D point (for hover/click).
        
        Args:
            point: 3D coordinates
            
        Returns:
            Dict with feature info or None
        """
        if not self._is_feature_mode_active or self._feature_analysis is None:
            return None
        
        try:
            # Find closest face to point
            import pyvista as pv
            
            mesh = self._original_mesh
            if mesh is None:
                return None
            
            # Get face centers
            centers = mesh.cell_centers().points
            
            # Find closest
            distances = np.linalg.norm(centers - np.array(point), axis=1)
            closest_face = np.argmin(distances)
            min_distance = distances[closest_face]
            
            # Check if close enough (within tolerance)
            tolerance = mesh.length * 0.01  # 1% of mesh size
            if min_distance > tolerance:
                return None
            
            # Find which feature this face belongs to
            return self._find_feature_by_face_index(closest_face)
            
        except Exception as e:
            logger.debug(f"Failed to get feature info at point: {e}")
            return None
    
    def _find_feature_by_face_index(self, face_idx: int) -> Optional[Dict]:
        """Find which feature contains the given face index."""
        analysis = self._feature_analysis
        if analysis is None:
            return None
        
        # Check base plane
        if (analysis.base_plane and 
            face_idx in analysis.base_plane.face_indices):
            return {
                "type": "base_plane",
                "index": 0,
                "feature": analysis.base_plane,
                "confidence": analysis.base_plane.confidence
            }
        
        # Check holes
        for i, hole in enumerate(analysis.holes):
            if face_idx in hole.face_indices:
                return {
                    "type": "hole",
                    "index": i,
                    "feature": hole,
                    "confidence": hole.confidence
                }
        
        # Check pockets
        for i, pocket in enumerate(analysis.pockets):
            if (face_idx in pocket.boundary_face_indices or
                face_idx in pocket.bottom_face_indices):
                return {
                    "type": "pocket",
                    "index": i,
                    "feature": pocket,
                    "confidence": pocket.confidence
                }
        
        return None
    
    def get_legend_info(self) -> List[Dict]:
        """
        Get legend information for UI display.
        
        Returns:
            List of dicts with color and label
        """
        scheme = self._color_scheme
        
        return [
            {
                "color": scheme.base_plane_high,
                "label": "Base Plane (>90% confidence)",
                "type": "base_plane"
            },
            {
                "color": scheme.hole_high,
                "label": "Hole (>90% confidence)",
                "type": "hole"
            },
            {
                "color": scheme.hole_medium,
                "label": "Hole (70-90% confidence)",
                "type": "hole"
            },
            {
                "color": scheme.pocket_high,
                "label": "Pocket (>90% confidence)",
                "type": "pocket"
            },
            {
                "color": scheme.uncertain,
                "label": "Uncertain (<70% confidence)",
                "type": "uncertain"
            },
        ]
    
    def get_feature_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about detected features.
        
        Returns:
            Dict with counts and confidence info
        """
        if self._feature_analysis is None:
            return {}
        
        analysis = self._feature_analysis
        
        holes_high = sum(1 for h in analysis.holes 
                        if h.confidence >= self.HIGH_CONFIDENCE)
        holes_medium = sum(1 for h in analysis.holes 
                          if self.MEDIUM_CONFIDENCE <= h.confidence < self.HIGH_CONFIDENCE)
        holes_low = sum(1 for h in analysis.holes 
                       if h.confidence < self.MEDIUM_CONFIDENCE)
        
        return {
            "total_features": (
                (1 if analysis.base_plane else 0) +
                len(analysis.holes) +
                len(analysis.pockets) +
                len(analysis.fillets)
            ),
            "base_plane": {
                "detected": analysis.base_plane is not None,
                "confidence": analysis.base_plane.confidence if analysis.base_plane else 0
            },
            "holes": {
                "total": len(analysis.holes),
                "high_confidence": holes_high,
                "medium_confidence": holes_medium,
                "low_confidence": holes_low,
            },
            "pockets": {
                "total": len(analysis.pockets),
            },
            "fillets": {
                "total": len(analysis.fillets),
            },
            "overall_confidence": analysis.overall_confidence,
            "requires_review": analysis.requires_user_review,
        }
    
    def _clear_feature_actors(self):
        """Remove feature actors from viewport."""
        try:
            # This would be implemented by the viewport class
            # that includes this mixin
            if hasattr(self, '_plotter') and self._plotter:
                for name, actor in self._feature_actors.items():
                    self._plotter.remove_actor(actor)
            self._feature_actors.clear()
        except Exception as e:
            logger.debug(f"Failed to clear feature actors: {e}")
    
    def set_hover_callback(self, callback: Callable):
        """Set callback for hover events."""
        self._hover_callback = callback
    
    def set_selection_callback(self, callback: Callable):
        """Set callback for selection events."""
        self._selection_callback = callback
    
    def is_feature_mode_active(self) -> bool:
        """Check if feature analysis mode is active."""
        return self._is_feature_mode_active
    
    def get_colored_mesh(self):
        """
        Get the colored mesh for display.
        
        Returns:
            PyVista mesh with cell_data colors or None
        """
        return self._feature_mesh
