"""
MashCAD - Mate Solver Module
============================

AS-003: Mate-Solver Base Kernel for Sprint 3.

Provides iterative constraint solving for assembly mates.
Resolves mate constraints between components and computes transforms.

Classes:
 - SolveResult: Dataclass containing solver results
 - MateSolver: Iterative constraint solver for assembly mates

Supported Mate Types:
 - COINCIDENT: Point A = Point B
 - PARALLEL: Normal A × Normal B = 0
 - PERPENDICULAR: Normal A · Normal B = 0
 - DISTANCE: |Point A - Point B| = d
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set
from enum import Enum
from loguru import logger

from modeling.mate_system import (
    Mate,
    MateType,
    MateStatus,
    MateReference,
    MateManager,
)
from modeling.component_core import Component, ComponentTransform


class SolveStatus(Enum):
    """Status of a solve operation."""
    SUCCESS = "success"
    PARTIAL = "partial"          # Some mates solved, others not
    FAILED = "failed"            # Solver failed to converge
    CONFLICT = "conflict"        # Conflicting constraints
    OVERCONSTRAINED = "overconstrained"


@dataclass
class GeometricEntity:
    """
    Represents a geometric entity for solving.
    
    Attributes:
        point: Origin point (x, y, z)
        direction: Direction vector for axes/faces (nx, ny, nz)
        entity_type: Type of entity ("point", "axis", "plane")
    """
    point: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    direction: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    entity_type: str = "point"
    
    def transformed(self, transform: ComponentTransform) -> "GeometricEntity":
        """Apply a transform to this entity and return a new entity."""
        # Apply rotation then translation
        new_point = self._apply_transform(self.point, transform)
        new_dir = self._apply_rotation(self.direction, transform)
        return GeometricEntity(
            point=new_point,
            direction=new_dir,
            entity_type=self.entity_type
        )
    
    def _apply_transform(
        self, 
        point: Tuple[float, float, float], 
        transform: ComponentTransform
    ) -> Tuple[float, float, float]:
        """Apply full transform (rotation + translation + scale) to a point."""
        rx, ry, rz = [math.radians(a) for a in transform.rotation]
        sx, sy, sz = transform.scale, transform.scale, transform.scale
        px, py, pz = point
        tx, ty, tz = transform.position
        
        # Rotation matrices (XYZ Euler angles)
        # Rotation around X
        cx, sx_rot = math.cos(rx), math.sin(rx)
        # Rotation around Y
        cy, sy_rot = math.cos(ry), math.sin(ry)
        # Rotation around Z
        cz, sz_rot = math.cos(rz), math.sin(rz)
        
        # Combined rotation matrix (Rz * Ry * Rx)
        # Apply to point
        x = (cy * cz) * px + (cy * sz_rot) * py + (-sy_rot) * pz
        y = (sx_rot * sy_rot * cz - cx * sz_rot) * px + (sx_rot * sy_rot * sz_rot + cx * cz) * py + (sx_rot * cy) * pz
        z = (cx * sy_rot * cz + sx_rot * sz_rot) * px + (cx * sy_rot * sz_rot - sx_rot * cz) * py + (cx * cy) * pz
        
        # Apply scale and translation
        return (x * sx + tx, y * sy + ty, z * sz + tz)
    
    def _apply_rotation(
        self, 
        vec: Tuple[float, float, float], 
        transform: ComponentTransform
    ) -> Tuple[float, float, float]:
        """Apply only rotation to a direction vector."""
        rx, ry, rz = [math.radians(a) for a in transform.rotation]
        vx, vy, vz = vec
        
        # Rotation matrices
        cx, sx_rot = math.cos(rx), math.sin(rx)
        cy, sy_rot = math.cos(ry), math.sin(rz)
        cz, sz_rot = math.cos(rz), math.sin(rz)
        
        # Combined rotation (Rz * Ry * Rx)
        x = (cy * cz) * vx + (cy * sz_rot) * vy + (-sy_rot) * vz
        y = (sx_rot * sy_rot * cz - cx * sz_rot) * vx + (sx_rot * sy_rot * sz_rot + cx * cz) * vy + (sx_rot * cy) * vz
        z = (cx * sy_rot * cz + sx_rot * sz_rot) * vx + (cx * sy_rot * sz_rot - sx_rot * cz) * vy + (cx * cy) * vz
        
        # Normalize
        length = math.sqrt(x*x + y*y + z*z)
        if length > 1e-10:
            return (x/length, y/length, z/length)
        return (x, y, z)


@dataclass
class SolveResult:
    """
    Result of a mate solving operation.
    
    Attributes:
        success: Whether solving was successful
        status: Detailed solve status
        component_transforms: Computed transforms for each component
        solved_mates: List of mates that were satisfied
        unsolved_mates: List of mates that could not be satisfied
        conflicts: List of detected conflicts
        iterations: Number of iterations used
        error: Error message if failed
        final_error: Final constraint error value
    """
    success: bool = False
    status: SolveStatus = SolveStatus.FAILED
    component_transforms: Dict[str, ComponentTransform] = field(default_factory=dict)
    solved_mates: List[Mate] = field(default_factory=list)
    unsolved_mates: List[Mate] = field(default_factory=list)
    conflicts: List[Tuple[str, str]] = field(default_factory=list)  # (mate_id, conflict_reason)
    iterations: int = 0
    error: Optional[str] = None
    final_error: float = float('inf')
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            "success": self.success,
            "status": self.status.value,
            "component_transforms": {
                k: v.to_dict() for k, v in self.component_transforms.items()
            },
            "solved_mates": [m.mate_id for m in self.solved_mates],
            "unsolved_mates": [m.mate_id for m in self.unsolved_mates],
            "conflicts": self.conflicts,
            "iterations": self.iterations,
            "error": self.error,
            "final_error": self.final_error,
        }


@dataclass
class SolverConfig:
    """Configuration for the mate solver."""
    max_iterations: int = 100
    tolerance: float = 1e-6
    learning_rate: float = 0.1
    damping: float = 0.5
    min_step: float = 1e-8
    angular_tolerance: float = 1e-4  # radians


class MateSolver:
    """
    Iterative constraint solver for assembly mates.
    
    Uses gradient descent to minimize constraint error and find
    component transforms that satisfy all mate constraints.
    
    Usage:
        solver = MateSolver()
        result = solver.solve(assembly_components, mates)
        if result.success:
            apply_transforms(result.component_transforms)
    """
    
    def __init__(self, config: Optional[SolverConfig] = None):
        """
        Initialize the mate solver.
        
        Args:
            config: Solver configuration (uses defaults if not provided)
        """
        self.config = config or SolverConfig()
        self._component_entities: Dict[str, GeometricEntity] = {}
        logger.debug(f"[MATE_SOLVER] Initialized with config: max_iter={self.config.max_iterations}")
    
    def solve(
        self,
        components: Dict[str, Component],
        mates: List[Mate],
        fixed_components: Optional[Set[str]] = None
    ) -> SolveResult:
        """
        Solve mate constraints for the given components.
        
        Args:
            components: Dictionary of component_id -> Component
            mates: List of mate constraints to solve
            fixed_components: Set of component IDs that should not be moved
        
        Returns:
            SolveResult with computed transforms and status
        """
        if not components:
            return SolveResult(
                success=False,
                status=SolveStatus.FAILED,
                error="No components to solve"
            )
        
        if not mates:
            # No mates - return identity transforms
            return SolveResult(
                success=True,
                status=SolveStatus.SUCCESS,
                component_transforms={
                    cid: comp.transform.copy() 
                    for cid, comp in components.items()
                },
                iterations=0,
                final_error=0.0
            )
        
        fixed_components = fixed_components or set()
        
        # Initialize transforms from current component state
        transforms: Dict[str, ComponentTransform] = {
            cid: comp.transform.copy() 
            for cid, comp in components.items()
        }
        
        # Build component graph and detect conflicts
        conflict_result = self._detect_conflicts(mates, components)
        if conflict_result:
            return conflict_result
        
        # Get movable components (not fixed)
        movable = [cid for cid in components.keys() if cid not in fixed_components]
        
        if not movable:
            # All components fixed - just validate
            error = self._compute_total_error(transforms, mates, components)
            return SolveResult(
                success=error < self.config.tolerance,
                status=SolveStatus.SUCCESS if error < self.config.tolerance else SolveStatus.FAILED,
                component_transforms=transforms,
                iterations=0,
                final_error=error
            )
        
        # Iterative solving
        best_transforms = transforms.copy()
        best_error = self._compute_total_error(transforms, mates, components)
        
        for iteration in range(self.config.max_iterations):
            # Compute gradients and update transforms
            gradients = self._compute_gradients(transforms, mates, components, movable)
            
            # Apply gradient descent step
            new_transforms = self._apply_gradients(
                transforms, gradients, movable
            )
            
            # Compute new error
            new_error = self._compute_total_error(new_transforms, mates, components)
            
            # Check for convergence
            if new_error < self.config.tolerance:
                logger.info(f"[MATE_SOLVER] Converged at iteration {iteration + 1}, error={new_error:.2e}")
                return self._build_success_result(
                    new_transforms, mates, components, iteration + 1, new_error
                )
            
            # Keep best solution
            if new_error < best_error:
                best_transforms = new_transforms.copy()
                best_error = new_error
            
            # Check for minimal progress
            improvement = abs(transforms[movable[0]].position[0] - new_transforms[movable[0]].position[0]) if movable else 0
            if improvement < self.config.min_step and new_error < self.config.tolerance * 100:
                # Close enough
                break
            
            transforms = new_transforms
        
        # Return best result found
        final_error = self._compute_total_error(best_transforms, mates, components)
        success = final_error < self.config.tolerance
        
        result = self._build_result(
            best_transforms, mates, components, 
            self.config.max_iterations, final_error, success
        )
        
        logger.info(f"[MATE_SOLVER] Finished: success={success}, error={final_error:.2e}")
        return result
    
    def _detect_conflicts(
        self, 
        mates: List[Mate], 
        components: Dict[str, Component]
    ) -> Optional[SolveResult]:
        """Detect obvious conflicts in mate constraints."""
        # Check for mates involving non-existent components
        for mate in mates:
            if mate.reference1 and mate.reference1.component_id not in components:
                return SolveResult(
                    success=False,
                    status=SolveStatus.FAILED,
                    error=f"Component '{mate.reference1.component_id}' not found in mate '{mate.name}'"
                )
            if mate.reference2 and mate.reference2.component_id not in components:
                return SolveResult(
                    success=False,
                    status=SolveStatus.FAILED,
                    error=f"Component '{mate.reference2.component_id}' not found in mate '{mate.name}'"
                )
        
        # Check for overconstrained components
        component_mates: Dict[str, List[Mate]] = {}
        for mate in mates:
            if mate.reference1:
                comp_id = mate.reference1.component_id
                if comp_id not in component_mates:
                    component_mates[comp_id] = []
                component_mates[comp_id].append(mate)
            if mate.reference2:
                comp_id = mate.reference2.component_id
                if comp_id not in component_mates:
                    component_mates[comp_id] = []
                component_mates[comp_id].append(mate)
        
        # A component with more than 6 mates is likely overconstrained (6 DOF)
        for comp_id, comp_mates in component_mates.items():
            unique_mates = list({m.mate_id for m in comp_mates})
            if len(unique_mates) > 6:
                logger.warning(f"[MATE_SOLVER] Component '{comp_id}' may be overconstrained with {len(unique_mates)} mates")
        
        return None
    
    def _compute_total_error(
        self,
        transforms: Dict[str, ComponentTransform],
        mates: List[Mate],
        components: Dict[str, Component]
    ) -> float:
        """Compute total constraint error for all mates."""
        total_error = 0.0
        
        for mate in mates:
            error = self._compute_mate_error(mate, transforms, components)
            total_error += error * error  # Squared error for gradient descent
        
        return math.sqrt(total_error) if total_error > 0 else 0.0
    
    def _compute_mate_error(
        self,
        mate: Mate,
        transforms: Dict[str, ComponentTransform],
        components: Dict[str, Component]
    ) -> float:
        """Compute error for a single mate constraint."""
        if not mate.reference1 or not mate.reference2:
            return 0.0
        
        # Get geometric entities for references
        entity1 = self._get_reference_entity(mate.reference1, components)
        entity2 = self._get_reference_entity(mate.reference2, components)
        
        # Transform entities
        t1 = transforms.get(mate.reference1.component_id, ComponentTransform())
        t2 = transforms.get(mate.reference2.component_id, ComponentTransform())
        
        te1 = entity1.transformed(t1)
        te2 = entity2.transformed(t2)
        
        # Compute error based on mate type
        if mate.mate_type == MateType.COINCIDENT:
            return self._coincident_error(te1, te2)
        elif mate.mate_type == MateType.PARALLEL:
            return self._parallel_error(te1, te2)
        elif mate.mate_type == MateType.PERPENDICULAR:
            return self._perpendicular_error(te1, te2)
        elif mate.mate_type == MateType.DISTANCE:
            distance = mate.parameters.get("distance", 0.0)
            return self._distance_error(te1, te2, distance)
        elif mate.mate_type == MateType.ANGLE:
            angle = mate.parameters.get("angle", 0.0)
            return self._angle_error(te1, te2, angle)
        elif mate.mate_type == MateType.ALIGN:
            return self._align_error(te1, te2)
        else:
            logger.warning(f"[MATE_SOLVER] Unsupported mate type: {mate.mate_type}")
            return 0.0
    
    def _coincident_error(
        self, 
        e1: GeometricEntity, 
        e2: GeometricEntity
    ) -> float:
        """COINCIDENT: Point A = Point B"""
        dx = e1.point[0] - e2.point[0]
        dy = e1.point[1] - e2.point[1]
        dz = e1.point[2] - e2.point[2]
        return math.sqrt(dx*dx + dy*dy + dz*dz)
    
    def _parallel_error(
        self, 
        e1: GeometricEntity, 
        e2: GeometricEntity
    ) -> float:
        """PARALLEL: Normal A × Normal B = 0 (cross product magnitude)"""
        d1, d2 = e1.direction, e2.direction
        # Cross product
        cx = d1[1] * d2[2] - d1[2] * d2[1]
        cy = d1[2] * d2[0] - d1[0] * d2[2]
        cz = d1[0] * d2[1] - d1[1] * d2[0]
        return math.sqrt(cx*cx + cy*cy + cz*cz)
    
    def _perpendicular_error(
        self, 
        e1: GeometricEntity, 
        e2: GeometricEntity
    ) -> float:
        """PERPENDICULAR: Normal A · Normal B = 0 (dot product)"""
        d1, d2 = e1.direction, e2.direction
        dot = d1[0]*d2[0] + d1[1]*d2[1] + d1[2]*d2[2]
        return abs(dot)
    
    def _distance_error(
        self, 
        e1: GeometricEntity, 
        e2: GeometricEntity,
        target_distance: float
    ) -> float:
        """DISTANCE: |Point A - Point B| = d"""
        actual = self._coincident_error(e1, e2)
        return abs(actual - target_distance)
    
    def _angle_error(
        self, 
        e1: GeometricEntity, 
        e2: GeometricEntity,
        target_angle_deg: float
    ) -> float:
        """ANGLE: Angle between directions = target"""
        d1, d2 = e1.direction, e2.direction
        dot = d1[0]*d2[0] + d1[1]*d2[1] + d1[2]*d2[2]
        dot = max(-1.0, min(1.0, dot))  # Clamp for numerical stability
        actual_angle = math.degrees(math.acos(dot))
        return abs(actual_angle - target_angle_deg)
    
    def _align_error(
        self, 
        e1: GeometricEntity, 
        e2: GeometricEntity
    ) -> float:
        """ALIGN: Combination of parallel and point alignment"""
        # Direction should be parallel (same or opposite)
        parallel_err = self._parallel_error(e1, e2)
        # Points should be on the same axis line
        # Project difference onto perpendicular plane
        dx = e1.point[0] - e2.point[0]
        dy = e1.point[1] - e2.point[1]
        dz = e1.point[2] - e2.point[2]
        # Use average direction
        ax = (e1.direction[0] + e2.direction[0]) / 2
        ay = (e1.direction[1] + e2.direction[1]) / 2
        az = (e1.direction[2] + e2.direction[2]) / 2
        length = math.sqrt(ax*ax + ay*ay + az*az)
        if length > 1e-10:
            ax, ay, az = ax/length, ay/length, az/length
        # Dot product gives parallel component
        parallel_comp = dx*ax + dy*ay + dz*az
        # Perpendicular error is total - parallel
        total_dist = math.sqrt(dx*dx + dy*dy + dz*dz)
        perp_dist = math.sqrt(max(0, total_dist*total_dist - parallel_comp*parallel_comp))
        return parallel_err + perp_dist * 0.5
    
    def _get_reference_entity(
        self,
        ref: MateReference,
        components: Dict[str, Component]
    ) -> GeometricEntity:
        """Get geometric entity for a mate reference."""
        # Default entity at origin
        entity = GeometricEntity(
            point=(0.0, 0.0, 0.0),
            direction=(0.0, 0.0, 1.0),
            entity_type=ref.reference_type
        )
        
        # In a full implementation, this would look up the actual geometry
        # from the component's body using the reference_id
        # For now, we use placeholder geometry based on reference type
        
        if ref.reference_type == "face":
            # Face: point on face, normal direction
            entity = GeometricEntity(
                point=(0.0, 0.0, 0.0),
                direction=(0.0, 0.0, 1.0),
                entity_type="plane"
            )
        elif ref.reference_type == "edge":
            # Edge: point on edge, tangent direction
            entity = GeometricEntity(
                point=(0.0, 0.0, 0.0),
                direction=(1.0, 0.0, 0.0),
                entity_type="axis"
            )
        elif ref.reference_type == "vertex":
            # Vertex: just a point
            entity = GeometricEntity(
                point=(0.0, 0.0, 0.0),
                direction=(0.0, 0.0, 1.0),
                entity_type="point"
            )
        elif ref.reference_type == "axis":
            # Axis: origin and direction
            entity = GeometricEntity(
                point=(0.0, 0.0, 0.0),
                direction=(0.0, 0.0, 1.0),
                entity_type="axis"
            )
        
        return entity
    
    def _compute_gradients(
        self,
        transforms: Dict[str, ComponentTransform],
        mates: List[Mate],
        components: Dict[str, Component],
        movable: List[str]
    ) -> Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
        """
        Compute gradients for each movable component.
        
        Returns dict of component_id -> (position_gradient, rotation_gradient)
        """
        gradients: Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = {}
        
        for comp_id in movable:
            pos_grad = [0.0, 0.0, 0.0]
            rot_grad = [0.0, 0.0, 0.0]
            
            for mate in mates:
                if not mate.involves_component(comp_id):
                    continue
                
                # Numerical gradient computation
                delta = 0.001
                
                # Position gradients
                for i in range(3):
                    # Positive delta
                    t_pos = transforms[comp_id].copy()
                    pos = list(t_pos.position)
                    pos[i] += delta
                    t_pos.position = tuple(pos)
                    transforms_pos = {**transforms, comp_id: t_pos}
                    err_pos = self._compute_total_error(transforms_pos, mates, components)
                    
                    # Negative delta
                    t_neg = transforms[comp_id].copy()
                    pos = list(t_neg.position)
                    pos[i] -= delta
                    t_neg.position = tuple(pos)
                    transforms_neg = {**transforms, comp_id: t_neg}
                    err_neg = self._compute_total_error(transforms_neg, mates, components)
                    
                    pos_grad[i] += (err_pos - err_neg) / (2 * delta)
                
                # Rotation gradients
                for i in range(3):
                    # Positive delta
                    t_pos = transforms[comp_id].copy()
                    rot = list(t_pos.rotation)
                    rot[i] += delta * 10  # Scale for degrees
                    t_pos.rotation = tuple(rot)
                    transforms_pos = {**transforms, comp_id: t_pos}
                    err_pos = self._compute_total_error(transforms_pos, mates, components)
                    
                    # Negative delta
                    t_neg = transforms[comp_id].copy()
                    rot = list(t_neg.rotation)
                    rot[i] -= delta * 10
                    t_neg.rotation = tuple(rot)
                    transforms_neg = {**transforms, comp_id: t_neg}
                    err_neg = self._compute_total_error(transforms_neg, mates, components)
                    
                    rot_grad[i] += (err_pos - err_neg) / (2 * delta * 10)
            
            gradients[comp_id] = (
                tuple(pos_grad),
                tuple(rot_grad)
            )
        
        return gradients
    
    def _apply_gradients(
        self,
        transforms: Dict[str, ComponentTransform],
        gradients: Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float]]],
        movable: List[str]
    ) -> Dict[str, ComponentTransform]:
        """Apply gradient descent step to transforms."""
        new_transforms = {}
        
        for comp_id in transforms:
            if comp_id not in movable:
                new_transforms[comp_id] = transforms[comp_id].copy()
                continue
            
            pos_grad, rot_grad = gradients.get(comp_id, ((0, 0, 0), (0, 0, 0)))
            t = transforms[comp_id].copy()
            
            # Apply gradient descent with damping
            lr = self.config.learning_rate
            damping = self.config.damping
            
            new_pos = tuple(
                t.position[i] - lr * pos_grad[i] * damping
                for i in range(3)
            )
            new_rot = tuple(
                t.rotation[i] - lr * rot_grad[i] * damping
                for i in range(3)
            )
            
            t.position = new_pos
            t.rotation = new_rot
            new_transforms[comp_id] = t
        
        return new_transforms
    
    def _build_success_result(
        self,
        transforms: Dict[str, ComponentTransform],
        mates: List[Mate],
        components: Dict[str, Component],
        iterations: int,
        final_error: float
    ) -> SolveResult:
        """Build a successful solve result."""
        return self._build_result(
            transforms, mates, components, iterations, final_error, True
        )
    
    def _build_result(
        self,
        transforms: Dict[str, ComponentTransform],
        mates: List[Mate],
        components: Dict[str, Component],
        iterations: int,
        final_error: float,
        success: bool
    ) -> SolveResult:
        """Build a solve result with mate classification."""
        solved_mates = []
        unsolved_mates = []
        conflicts = []
        
        tolerance = self.config.tolerance * 10  # Slightly relaxed for classification
        
        for mate in mates:
            error = self._compute_mate_error(mate, transforms, components)
            if error < tolerance:
                solved_mates.append(mate)
            else:
                unsolved_mates.append(mate)
                conflicts.append((mate.mate_id, f"Error: {error:.4f}"))
        
        # Determine status
        if success and not unsolved_mates:
            status = SolveStatus.SUCCESS
        elif solved_mates and unsolved_mates:
            status = SolveStatus.PARTIAL
        elif not solved_mates:
            status = SolveStatus.FAILED
        else:
            status = SolveStatus.SUCCESS
        
        return SolveResult(
            success=success and not unsolved_mates,
            status=status,
            component_transforms=transforms,
            solved_mates=solved_mates,
            unsolved_mates=unsolved_mates,
            conflicts=conflicts,
            iterations=iterations,
            final_error=final_error,
        )


def solve_assembly(
    components: Dict[str, Component],
    mates: List[Mate],
    fixed_components: Optional[Set[str]] = None
) -> SolveResult:
    """
    Convenience function to solve an assembly.
    
    Args:
        components: Dictionary of component_id -> Component
        mates: List of mate constraints
        fixed_components: Set of component IDs that should not be moved
    
    Returns:
        SolveResult with computed transforms
    """
    solver = MateSolver()
    return solver.solve(components, mates, fixed_components)
