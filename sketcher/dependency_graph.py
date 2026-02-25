"""
Dependency Graph for Incremental Constraint Solving

Tracks which constraints depend on which geometric entities.
Enables incremental solving by identifying affected constraints during dragging.
W35 P4: Incremental Solver Support
"""

from typing import Dict, Set, List, Any, Tuple
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class EntityInfo:
    """Information about a geometric entity"""
    id: str
    type: str  # 'point', 'line', 'circle', 'arc', etc.
    obj: Any
    related_constraints: Set[str] = field(default_factory=set)

    def __hash__(self):
        return hash(self.id)


class DependencyGraph:
    """
    Dependency graph for constraint-entity relationships.

    Enables incremental solving by:
    1. Tracking which constraints depend on which entities
    2. Finding affected constraints when an entity changes
    3. Computing constraint subsets for efficient solving
    """

    def __init__(self):
        # Entity ID -> EntityInfo
        self._entities: Dict[str, EntityInfo] = {}

        # Constraint ID -> Set of Entity IDs
        self._constraint_entities: Dict[str, Set[str]] = {}

        # Adjacency: Entity ID -> Set of directly connected Entity IDs
        self._adjacency: Dict[str, Set[str]] = {}

        # Cache for affected constraints
        self._affected_cache: Dict[str, Set[str]] = {}

    def clear(self):
        """Clear all data"""
        self._entities.clear()
        self._constraint_entities.clear()
        self._adjacency.clear()
        self._affected_cache.clear()

    @staticmethod
    def _normalize_id(raw_id: Any) -> str:
        """Normalize IDs to stable string keys."""
        if raw_id is None:
            return ""
        return str(raw_id)

    def _entity_id(self, entity: Any) -> str:
        """Extract normalized entity ID."""
        if entity is None:
            return ""
        if hasattr(entity, "id"):
            return self._normalize_id(entity.id)
        return self._normalize_id(id(entity))

    def _constraint_id(self, constraint: Any) -> str:
        """Extract normalized constraint ID."""
        if constraint is None:
            return ""
        if hasattr(constraint, "id"):
            return self._normalize_id(constraint.id)
        return self._normalize_id(id(constraint))

    @staticmethod
    def _infer_entity_type(entity: Any) -> str:
        """Best-effort entity type inference for lazily registered objects."""
        cls_name = entity.__class__.__name__.lower() if entity is not None else ""
        if "point" in cls_name:
            return "point"
        if "line" in cls_name:
            return "line"
        if "circle" in cls_name:
            return "circle"
        if "arc" in cls_name:
            return "arc"
        if "ellipse" in cls_name:
            return "ellipse"
        if "spline" in cls_name:
            return "spline"
        return "entity"

    def build_from_sketch(self, sketch) -> None:
        """
        Build dependency graph from a sketch.

        Args:
            sketch: Sketch object with points, lines, circles, arcs, constraints
        """
        self.clear()

        # Phase 1: Register all entities
        self._register_entities(sketch)

        # Phase 2: Register all constraints
        self._register_constraints(sketch)

        # Phase 3: Build adjacency (entity-entity connections via constraints)
        self._build_adjacency()

        logger.debug(f"[DependencyGraph] Built: {len(self._entities)} entities, "
                    f"{len(self._constraint_entities)} constraints")

    def _register_entities(self, sketch) -> None:
        """Register all geometric entities from sketch"""
        # Points
        for p in getattr(sketch, "points", []):
            self._add_entity(self._entity_id(p), 'point', p)

        # Lines (also register their endpoints)
        for line in getattr(sketch, "lines", []):
            line_id = self._entity_id(line)
            self._add_entity(line_id, 'line', line)
            # Line endpoints are points, already registered above
            if hasattr(line, 'start') and line.start:
                start_id = self._entity_id(line.start)
                self._add_entity(start_id, 'point', line.start)
                self._connect_entities(line_id, start_id)
            if hasattr(line, 'end') and line.end:
                end_id = self._entity_id(line.end)
                self._add_entity(end_id, 'point', line.end)
                self._connect_entities(line_id, end_id)
                if hasattr(line, 'start') and line.start:
                    self._connect_entities(self._entity_id(line.start), end_id)

        # Circles
        for circle in getattr(sketch, "circles", []):
            circle_id = self._entity_id(circle)
            self._add_entity(circle_id, 'circle', circle)
            if hasattr(circle, 'center') and circle.center:
                center_id = self._entity_id(circle.center)
                self._add_entity(center_id, 'point', circle.center)
                self._connect_entities(circle_id, center_id)

        # Arcs
        for arc in getattr(sketch, "arcs", []):
            arc_id = self._entity_id(arc)
            self._add_entity(arc_id, 'arc', arc)
            if hasattr(arc, 'center') and arc.center:
                center_id = self._entity_id(arc.center)
                self._add_entity(center_id, 'point', arc.center)
                self._connect_entities(arc_id, center_id)

        # Ellipses
        for ellipse in getattr(sketch, "ellipses", []):
            ellipse_id = self._entity_id(ellipse)
            self._add_entity(ellipse_id, 'ellipse', ellipse)
            if hasattr(ellipse, 'center') and ellipse.center:
                center_id = self._entity_id(ellipse.center)
                self._add_entity(center_id, 'point', ellipse.center)
                self._connect_entities(ellipse_id, center_id)

        # Splines
        for spline in getattr(sketch, "splines", []):
            spline_id = self._entity_id(spline)
            self._add_entity(spline_id, 'spline', spline)
            for cp in getattr(spline, "control_points", []):
                cp_id = self._entity_id(cp)
                self._add_entity(cp_id, 'point', cp)
                self._connect_entities(spline_id, cp_id)

        # Native splines
        for ns in getattr(sketch, "native_splines", []):
            self._add_entity(self._entity_id(ns), 'native_spline', ns)

    def _add_entity(self, entity_id: str, entity_type: str, obj: Any) -> None:
        """Add an entity to the graph"""
        entity_id = self._normalize_id(entity_id)
        if not entity_id:
            return
        if entity_id not in self._entities:
            self._entities[entity_id] = EntityInfo(
                id=entity_id,
                type=entity_type,
                obj=obj
            )
        self._adjacency.setdefault(entity_id, set())

    def _connect_entities(self, entity_a: str, entity_b: str) -> None:
        """Add an undirected connectivity edge between two entities."""
        entity_a = self._normalize_id(entity_a)
        entity_b = self._normalize_id(entity_b)
        if not entity_a or not entity_b or entity_a == entity_b:
            return
        self._adjacency.setdefault(entity_a, set()).add(entity_b)
        self._adjacency.setdefault(entity_b, set()).add(entity_a)

    def _register_constraints(self, sketch) -> None:
        """Register all constraints and their entity relationships"""
        for constraint in getattr(sketch, "constraints", []):
            if not getattr(constraint, 'enabled', True):
                continue
            if not constraint.is_valid():
                continue

            constraint_id = self._constraint_id(constraint)
            entity_ids = set()

            # Extract entities from constraint
            for entity in getattr(constraint, 'entities', []):
                if entity is None:
                    continue

                eid = self._entity_id(entity)
                if not eid:
                    continue

                entity_ids.add(eid)

                # Register relationship
                if eid not in self._entities:
                    self._add_entity(eid, self._infer_entity_type(entity), entity)
                self._entities[eid].related_constraints.add(constraint_id)

            # Special handling for constraints with geometric selectors
            # (e.g., arc tangent with edge selection)
            self._extract_geometric_entities(constraint, entity_ids)

            self._constraint_entities[constraint_id] = entity_ids

    def _extract_geometric_entities(self, constraint, entity_ids: Set[str]) -> None:
        """Extract entities from geometric selectors in constraints"""
        # Some constraints use geometric selectors instead of direct entity references
        # For example, tangent constraints may have edge selections

        if hasattr(constraint, 'edge_selections'):
            for edge_sel in constraint.edge_selections:
                if hasattr(edge_sel, 'shape_id'):
                    entity_ids.add(self._normalize_id(edge_sel.shape_id))

        # Value-based constraints (length, distance, etc.) may reference entities
        if hasattr(constraint, 'value_entity'):
            if constraint.value_entity:
                entity_ids.add(self._entity_id(constraint.value_entity))

    def _build_adjacency(self) -> None:
        """Build entity-entity adjacency via shared constraints"""
        for constraint_id, entity_ids in self._constraint_entities.items():
            # All entities in this constraint are connected to each other
            entity_list = list(entity_ids)
            for i, e1 in enumerate(entity_list):
                for e2 in entity_list[i+1:]:
                    self._adjacency.setdefault(e1, set()).add(e2)
                    self._adjacency.setdefault(e2, set()).add(e1)

    def get_affected_constraints(self, entity_id: str) -> Set[str]:
        """
        Get all constraints affected by changes to an entity.

        Args:
            entity_id: ID of the entity that changed

        Returns:
            Set of constraint IDs that depend on this entity
        """
        entity_id = self._normalize_id(entity_id)
        # Check cache first
        if entity_id in self._affected_cache:
            return self._affected_cache[entity_id]

        affected = set()

        if entity_id in self._entities:
            affected = self._entities[entity_id].related_constraints.copy()

        # Also consider transitive dependencies (connected entities)
        # For example: moving a point affects lines connected to it
        for connected_id in self._adjacency.get(entity_id, set()):
            if connected_id in self._entities:
                affected.update(self._entities[connected_id].related_constraints)

        self._affected_cache[entity_id] = affected
        return affected

    def get_affected_entities(self, entity_id: str, max_depth: int = 2) -> Set[str]:
        """
        Get all entities affected by changes to an entity (BFS traversal).

        Args:
            entity_id: ID of the entity that changed
            max_depth: How many hops to traverse (default: 2)

        Returns:
            Set of affected entity IDs
        """
        entity_id = self._normalize_id(entity_id)
        visited = set()
        queue = [(entity_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)

            if current_id in visited or depth > max_depth:
                continue

            visited.add(current_id)

            # Add neighbors
            for neighbor_id in self._adjacency.get(current_id, set()):
                if neighbor_id not in visited:
                    queue.append((neighbor_id, depth + 1))

        visited.discard(entity_id)  # Remove the original entity
        return visited

    def get_constraint_subset(self, entity_ids: List[str]) -> Set[str]:
        """
        Get all constraints that involve any of the given entities.

        Args:
            entity_ids: List of entity IDs

        Returns:
            Set of constraint IDs
        """
        affected = set()
        for eid in entity_ids:
            affected.update(self.get_affected_constraints(eid))
        return affected

    def get_independent_subsets(self) -> List[Set[str]]:
        """
        Partition constraints into independent subsets.

        Useful for parallel solving or identifying clusters.

        Returns:
            List of constraint ID sets, where each set is independent
        """
        # Build constraint adjacency (constraints sharing entities)
        constraint_adj: Dict[str, Set[str]] = {}

        for c1_id, e1_ids in self._constraint_entities.items():
            constraint_adj.setdefault(c1_id, set())
            for c2_id, e2_ids in self._constraint_entities.items():
                if c1_id >= c2_id:
                    continue
                # If constraints share any entity, they're connected
                if e1_ids & e2_ids:
                    constraint_adj[c1_id].add(c2_id)
                    constraint_adj.setdefault(c2_id, set()).add(c1_id)

        # Find connected components
        visited = set()
        components = []

        for c_id in self._constraint_entities:
            if c_id in visited:
                continue

            # BFS to find component
            component = set()
            queue = [c_id]

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue

                visited.add(current)
                component.add(current)

                for neighbor in constraint_adj.get(current, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)

            components.append(component)

        return components

    def get_entity_info(self, entity_id: str) -> EntityInfo:
        """Get information about an entity"""
        return self._entities.get(self._normalize_id(entity_id))

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the dependency graph"""
        return {
            'entities': len(self._entities),
            'constraints': len(self._constraint_entities),
            'avg_constraints_per_entity': sum(
                len(ei.related_constraints) for ei in self._entities.values()
            ) / max(1, len(self._entities)),
            'max_constraints_per_entity': max(
                (len(ei.related_constraints) for ei in self._entities.values()),
                default=0
            ),
            'independent_subsets': len(self.get_independent_subsets())
        }

    def visualize(self) -> str:
        """
        Generate a text representation of the graph (for debugging).

        Returns:
            String representation of the graph structure
        """
        lines = ["Dependency Graph:", ""]

        # Show entities with their constraints
        lines.append("Entities:")
        for eid, info in sorted(self._entities.items()):
            constraints = info.related_constraints
            lines.append(f"  {eid} ({info.type}): {len(constraints)} constraints")

        # Show constraints with their entities
        lines.append("\nConstraints:")
        for cid, eids in sorted(self._constraint_entities.items()):
            lines.append(f"  {cid}: {len(eids)} entities")

        # Show adjacency
        lines.append("\nAdjacency (sample):")
        count = 0
        for eid, neighbors in sorted(self._adjacency.items()):
            if count >= 10:  # Limit output
                break
            lines.append(f"  {eid} -> {len(neighbors)} neighbors")
            count += 1

        return "\n".join(lines)


class IncrementalSolverContext:
    """
    Context manager for incremental solving during drag operations.

    Maintains state between drag frames:
    - Last solution (for warm starts)
    - Active constraint subset
    - Entity positions at drag start
    """

    def __init__(self, sketch, initial_entity_id: str = None):
        """
        Initialize incremental solve context.

        Args:
            sketch: The sketch being edited
            initial_entity_id: Entity being dragged (optional, can set later)
        """
        self.sketch = sketch
        self.dragged_entity_id = None

        # Build dependency graph
        self.graph = DependencyGraph()
        self.graph.build_from_sketch(sketch)

        # Active constraint subset (affected by drag)
        self.active_constraints: Set[str] = set()
        self.active_variables: Set[str] = set()

        # Solution state
        self.last_solution: Dict[str, float] = {}
        self.initial_positions: Dict[str, Tuple[float, ...]] = {}

        # Performance tracking
        self.solve_count = 0
        self.total_time_ms = 0.0

        if initial_entity_id is not None:
            self.set_dragged_entity(initial_entity_id)

    def set_dragged_entity(self, entity_id: str) -> None:
        """Set which entity is being dragged and update active subset"""
        entity_id = self.graph._normalize_id(entity_id)
        self.dragged_entity_id = entity_id

        # Get affected constraints
        self.active_constraints = self.graph.get_affected_constraints(entity_id)

        # Get affected entities (for variable tracking)
        affected_entities = self.graph.get_affected_entities(entity_id, max_depth=2)
        affected_entities.add(entity_id)
        for constraint_id in self.active_constraints:
            affected_entities.update(self.graph._constraint_entities.get(constraint_id, set()))
        self.active_variables = affected_entities

        # Store initial positions
        self._store_initial_positions()

        logger.debug(f"[IncrementalSolver] Dragging {entity_id}: "
                    f"{len(self.active_constraints)} constraints, "
                    f"{len(self.active_variables)} variables affected")

    def _store_initial_positions(self) -> None:
        """Store initial positions of all points for potential rollback"""
        self.initial_positions.clear()

        for p in self.sketch.points:
            self.initial_positions[p.id] = (p.x, p.y)

        # Also store circle radii, arc angles
        for circle in self.sketch.circles:
            self.initial_positions[f"{circle.id}_radius"] = (circle.radius,)

        for arc in self.sketch.arcs:
            self.initial_positions[f"{arc.id}_radius"] = (arc.radius,)
            self.initial_positions[f"{arc.id}_start_angle"] = (arc.start_angle,)
            self.initial_positions[f"{arc.id}_end_angle"] = (arc.end_angle,)

    def restore_initial_positions(self) -> None:
        """Restore all entities to their drag-start positions"""
        for p in self.sketch.points:
            if p.id in self.initial_positions:
                p.x, p.y = self.initial_positions[p.id]

        for circle in self.sketch.circles:
            key = f"{circle.id}_radius"
            if key in self.initial_positions:
                circle.radius = self.initial_positions[key][0]

        for arc in self.sketch.arcs:
            key = f"{arc.id}_radius"
            if key in self.initial_positions:
                arc.radius = self.initial_positions[key][0]
            key = f"{arc.id}_start_angle"
            if key in self.initial_positions:
                arc.start_angle = self.initial_positions[key][0]
            key = f"{arc.id}_end_angle"
            if key in self.initial_positions:
                arc.end_angle = self.initial_positions[key][0]

    def get_active_constraint_objects(self) -> List:
        """
        Get the actual constraint objects for the active subset.

        Returns:
            List of Constraint objects
        """
        active = []
        for c in self.sketch.constraints:
            cid = self.graph._constraint_id(c)
            if cid in self.active_constraints:
                active.append(c)
        return active

    def get_active_variables_dict(self) -> Dict[str, Any]:
        """
        Get all variables (points, etc.) that are part of the active subset.

        Returns:
            Dict mapping variable ID to object
        """
        variables = {}

        # Points
        for p in self.sketch.points:
            p_id = self.graph._entity_id(p)
            if p_id in self.active_variables and not getattr(p, "fixed", False):
                variables[f"{p.id}_x"] = (p, 'x')
                variables[f"{p.id}_y"] = (p, 'y')

        # Circles
        for circle in self.sketch.circles:
            circle_id = self.graph._entity_id(circle)
            if circle_id in self.active_variables:
                variables[f"{circle.id}_radius"] = (circle, 'radius')

        # Arcs
        for arc in self.sketch.arcs:
            arc_id = self.graph._entity_id(arc)
            if arc_id in self.active_variables:
                variables[f"{arc.id}_radius"] = (arc, 'radius')
                variables[f"{arc.id}_start_angle"] = (arc, 'start_angle')
                variables[f"{arc.id}_end_angle"] = (arc, 'end_angle')

        return variables

    def save_solution(self, solution_vector) -> None:
        """Store solution for next frame warm start"""
        self.last_solution.clear()
        for i, val in enumerate(solution_vector):
            self.last_solution[f"var_{i}"] = float(val)

    def get_warm_start(self, n_vars: int) -> List[float]:
        """Get warm start values from last solution"""
        if n_vars <= 0:
            return []
        if len(self.last_solution) >= n_vars:
            return [self.last_solution.get(f"var_{i}", 0.0) for i in range(n_vars)]
        return []
