"""
MashCAD - Mate System V1
========================

Assembly mate system for defining relationships between components.

AS-002: Mate-System V1 Scope Definition
Defines mate types, references, and the mate manager for assembly constraints.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Any
import uuid
import logging

logger = logging.getLogger(__name__)


class MateType(Enum):
    """Types of assembly mate constraints."""
    COINCIDENT = auto()      # Points/faces coincide
    PARALLEL = auto()        # Faces/axes parallel
    PERPENDICULAR = auto()   # Faces/axes perpendicular
    DISTANCE = auto()        # Fixed distance between
    ANGLE = auto()           # Fixed angle between
    TANGENT = auto()         # Tangent contact
    ALIGN = auto()           # Axis/face alignment


class MateStatus(Enum):
    """Status of a mate constraint."""
    OK = auto()              # Mate satisfied
    WARNING = auto()         # Near tolerance
    ERROR = auto()           # Cannot satisfy
    CONFLICT = auto()        # Conflicts with other mates


@dataclass
class MateReference:
    """
    Reference to a geometric entity on a component.
    
    Attributes:
        component_id: UUID of the component in the assembly
        reference_type: Type of geometric reference ("face", "edge", "vertex", "axis")
        reference_id: Unique identifier for the specific geometry (e.g., face hash, edge ID)
    """
    component_id: str
    reference_type: str  # "face", "edge", "vertex", "axis"
    reference_id: str
    
    def __post_init__(self):
        """Validate reference type."""
        valid_types = {"face", "edge", "vertex", "axis"}
        if self.reference_type not in valid_types:
            raise ValueError(f"Invalid reference_type: {self.reference_type}. "
                           f"Must be one of {valid_types}")
    
    def to_dict(self) -> Dict[str, str]:
        """Serialize to dictionary."""
        return {
            "component_id": self.component_id,
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "MateReference":
        """Deserialize from dictionary."""
        return cls(
            component_id=data["component_id"],
            reference_type=data["reference_type"],
            reference_id=data["reference_id"],
        )


@dataclass
class MateConflict:
    """
    Represents a conflict between two or more mates.
    
    Attributes:
        mate_ids: List of conflicting mate IDs
        conflict_type: Type of conflict (e.g., "overconstrained", "incompatible")
        description: Human-readable description of the conflict
    """
    mate_ids: List[str]
    conflict_type: str
    description: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "mate_ids": self.mate_ids,
            "conflict_type": self.conflict_type,
            "description": self.description,
        }


@dataclass
class Mate:
    """
    Assembly mate constraint between two component references.
    
    Attributes:
        mate_id: Unique identifier for this mate
        mate_type: Type of constraint (coincident, parallel, etc.)
        reference1: First component reference
        reference2: Second component reference
        parameters: Additional parameters (distance, angle, offset, etc.)
        status: Current status of the mate
        name: Optional human-readable name
    """
    mate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mate_type: MateType = MateType.COINCIDENT
    reference1: Optional[MateReference] = None
    reference2: Optional[MateReference] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: MateStatus = MateStatus.OK
    name: str = ""
    
    def __post_init__(self):
        """Set default name if not provided."""
        if not self.name:
            self.name = f"{self.mate_type.name}_{self.mate_id[:8]}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for persistence."""
        return {
            "mate_id": self.mate_id,
            "mate_type": self.mate_type.name,
            "reference1": self.reference1.to_dict() if self.reference1 else None,
            "reference2": self.reference2.to_dict() if self.reference2 else None,
            "parameters": self.parameters,
            "status": self.status.name,
            "name": self.name,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Mate":
        """Deserialize from dictionary."""
        ref1_data = data.get("reference1")
        ref2_data = data.get("reference2")
        
        return cls(
            mate_id=data["mate_id"],
            mate_type=MateType[data["mate_type"]],
            reference1=MateReference.from_dict(ref1_data) if ref1_data else None,
            reference2=MateReference.from_dict(ref2_data) if ref2_data else None,
            parameters=data.get("parameters", {}),
            status=MateStatus[data.get("status", "OK")],
            name=data.get("name", ""),
        )
    
    def involves_component(self, component_id: str) -> bool:
        """Check if this mate involves the given component."""
        return (
            (self.reference1 and self.reference1.component_id == component_id) or
            (self.reference2 and self.reference2.component_id == component_id)
        )
    
    def get_other_component(self, component_id: str) -> Optional[str]:
        """Get the other component ID in this mate relationship."""
        if self.reference1 and self.reference1.component_id == component_id:
            return self.reference2.component_id if self.reference2 else None
        if self.reference2 and self.reference2.component_id == component_id:
            return self.reference1.component_id if self.reference1 else None
        return None


class MateManager:
    """
    Manager for assembly mate constraints.
    
    Handles creation, deletion, validation, and conflict detection for mates.
    
    Usage:
        manager = MateManager()
        
        # Create a coincident mate between two component faces
        ref1 = MateReference("comp-1", "face", "face-hash-1")
        ref2 = MateReference("comp-2", "face", "face-hash-2")
        mate = manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        
        # Validate and check for conflicts
        status = manager.validate_mate(mate)
        conflicts = manager.get_mate_conflicts()
    """
    
    def __init__(self):
        """Initialize the mate manager."""
        self._mates: Dict[str, Mate] = {}
        self._component_index: Dict[str, List[str]] = {}  # component_id -> mate_ids
        logger.debug("MateManager initialized")
    
    def create_mate(
        self,
        mate_type: MateType,
        reference1: MateReference,
        reference2: MateReference,
        **params
    ) -> Mate:
        """
        Create a new mate between two component references.
        
        Args:
            mate_type: Type of constraint
            reference1: First component reference
            reference2: Second component reference
            **params: Additional parameters (distance, angle, etc.)
            
        Returns:
            The created Mate object
            
        Raises:
            ValueError: If references are invalid or same component
        """
        # Validate references are for different components
        if reference1.component_id == reference2.component_id:
            raise ValueError(
                f"Cannot create mate: both references point to the same component "
                f"'{reference1.component_id}'"
            )
        
        # Validate parameters based on mate type
        self._validate_mate_parameters(mate_type, params)
        
        # Create the mate
        mate = Mate(
            mate_type=mate_type,
            reference1=reference1,
            reference2=reference2,
            parameters=params,
            status=MateStatus.OK,
        )
        
        # Store the mate
        self._mates[mate.mate_id] = mate
        
        # Update component index
        self._add_to_component_index(mate.mate_id, reference1.component_id)
        self._add_to_component_index(mate.mate_id, reference2.component_id)
        
        logger.info(
            f"Created mate '{mate.name}' ({mate.mate_type.name}) between "
            f"{reference1.component_id} and {reference2.component_id}"
        )
        
        return mate
    
    def delete_mate(self, mate_id: str) -> bool:
        """
        Delete a mate by its ID.
        
        Args:
            mate_id: The ID of the mate to delete
            
        Returns:
            True if the mate was deleted, False if not found
        """
        if mate_id not in self._mates:
            logger.warning(f"Cannot delete mate: '{mate_id}' not found")
            return False
        
        mate = self._mates[mate_id]
        
        # Remove from component index
        if mate.reference1:
            self._remove_from_component_index(mate_id, mate.reference1.component_id)
        if mate.reference2:
            self._remove_from_component_index(mate_id, mate.reference2.component_id)
        
        # Remove the mate
        del self._mates[mate_id]
        
        logger.info(f"Deleted mate '{mate.name}' ({mate_id})")
        return True
    
    def get_mate(self, mate_id: str) -> Optional[Mate]:
        """
        Get a mate by its ID.
        
        Args:
            mate_id: The ID of the mate
            
        Returns:
            The Mate object or None if not found
        """
        return self._mates.get(mate_id)
    
    def get_all_mates(self) -> List[Mate]:
        """
        Get all mates.
        
        Returns:
            List of all Mate objects
        """
        return list(self._mates.values())
    
    def get_mates_for_component(self, component_id: str) -> List[Mate]:
        """
        Get all mates involving a specific component.
        
        Args:
            component_id: The component ID to search for
            
        Returns:
            List of Mate objects involving the component
        """
        mate_ids = self._component_index.get(component_id, [])
        return [self._mates[mid] for mid in mate_ids if mid in self._mates]
    
    def validate_mate(self, mate: Mate) -> MateStatus:
        """
        Validate a mate and update its status.
        
        This performs basic validation checks:
        - References are valid and point to existing components
        - Parameters are valid for the mate type
        - No obvious conflicts with existing mates
        
        Args:
            mate: The mate to validate
            
        Returns:
            The validation status
        """
        # Check references exist
        if not mate.reference1 or not mate.reference2:
            mate.status = MateStatus.ERROR
            logger.warning(f"Mate '{mate.mate_id}' missing references")
            return MateStatus.ERROR
        
        # Check for same component
        if mate.reference1.component_id == mate.reference2.component_id:
            mate.status = MateStatus.ERROR
            logger.warning(f"Mate '{mate.mate_id}' references same component")
            return MateStatus.ERROR
        
        # Validate parameters
        try:
            self._validate_mate_parameters(mate.mate_type, mate.parameters)
        except ValueError as e:
            mate.status = MateStatus.ERROR
            logger.warning(f"Mate '{mate.mate_id}' has invalid parameters: {e}")
            return MateStatus.ERROR
        
        # Check for conflicts with existing mates
        conflicts = self._find_conflicts_for_mate(mate)
        if conflicts:
            mate.status = MateStatus.CONFLICT
            logger.warning(f"Mate '{mate.mate_id}' has conflicts: {conflicts}")
            return MateStatus.CONFLICT
        
        mate.status = MateStatus.OK
        return MateStatus.OK
    
    def get_mate_conflicts(self) -> List[MateConflict]:
        """
        Find all conflicts between mates.
        
        Returns:
            List of MateConflict objects describing the conflicts
        """
        conflicts: List[MateConflict] = []
        processed_pairs: set = set()
        
        for mate in self._mates.values():
            mate_conflicts = self._find_conflicts_for_mate(mate)
            for conflict in mate_conflicts:
                # Create a unique key for this conflict pair
                pair_key = tuple(sorted(conflict.get("mate_ids", [])))
                if pair_key not in processed_pairs:
                    processed_pairs.add(pair_key)
                    conflicts.append(MateConflict(
                        mate_ids=list(pair_key),
                        conflict_type=conflict.get("type", "unknown"),
                        description=conflict.get("description", ""),
                    ))
        
        return conflicts
    
    def clear_all_mates(self) -> None:
        """Remove all mates from the manager."""
        self._mates.clear()
        self._component_index.clear()
        logger.info("All mates cleared")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the mate manager state to a dictionary.
        
        Returns:
            Dictionary containing all mate data
        """
        return {
            "mates": [mate.to_dict() for mate in self._mates.values()],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MateManager":
        """
        Deserialize a mate manager from a dictionary.
        
        Args:
            data: Dictionary containing mate data
            
        Returns:
            A new MateManager instance
        """
        manager = cls()
        
        for mate_data in data.get("mates", []):
            mate = Mate.from_dict(mate_data)
            manager._mates[mate.mate_id] = mate
            
            # Rebuild component index
            if mate.reference1:
                manager._add_to_component_index(mate.mate_id, mate.reference1.component_id)
            if mate.reference2:
                manager._add_to_component_index(mate.mate_id, mate.reference2.component_id)
        
        logger.info(f"Loaded {len(manager._mates)} mates from data")
        return manager
    
    # Private helper methods
    # ======================
    
    def _add_to_component_index(self, mate_id: str, component_id: str) -> None:
        """Add a mate ID to the component index."""
        if component_id not in self._component_index:
            self._component_index[component_id] = []
        if mate_id not in self._component_index[component_id]:
            self._component_index[component_id].append(mate_id)
    
    def _remove_from_component_index(self, mate_id: str, component_id: str) -> None:
        """Remove a mate ID from the component index."""
        if component_id in self._component_index:
            if mate_id in self._component_index[component_id]:
                self._component_index[component_id].remove(mate_id)
            if not self._component_index[component_id]:
                del self._component_index[component_id]
    
    def _validate_mate_parameters(self, mate_type: MateType, params: Dict[str, Any]) -> None:
        """
        Validate parameters for a mate type.
        
        Args:
            mate_type: The type of mate
            params: The parameters to validate
            
        Raises:
            ValueError: If parameters are invalid
        """
        if mate_type == MateType.DISTANCE:
            if "distance" not in params:
                raise ValueError("DISTANCE mate requires 'distance' parameter")
            if not isinstance(params["distance"], (int, float)):
                raise ValueError("distance must be a number")
        
        elif mate_type == MateType.ANGLE:
            if "angle" not in params:
                raise ValueError("ANGLE mate requires 'angle' parameter")
            if not isinstance(params["angle"], (int, float)):
                raise ValueError("angle must be a number")
    
    def _find_conflicts_for_mate(self, mate: Mate) -> List[Dict[str, Any]]:
        """
        Find conflicts for a specific mate.
        
        This implements basic conflict detection:
        - Overconstrained: Too many mates on the same DOF
        - Incompatible: Mates that cannot be satisfied together
        
        Args:
            mate: The mate to check
            
        Returns:
            List of conflict dictionaries
        """
        conflicts = []
        
        if not mate.reference1 or not mate.reference2:
            return conflicts
        
        # Get all mates involving the same components
        component1_mates = self.get_mates_for_component(mate.reference1.component_id)
        component2_mates = self.get_mates_for_component(mate.reference2.component_id)
        
        # Find mates that connect the same two components
        same_connection_mates = []
        for other_mate in component1_mates:
            if other_mate.mate_id == mate.mate_id:
                continue
            other_component = other_mate.get_other_component(mate.reference1.component_id)
            if other_component == mate.reference2.component_id:
                same_connection_mates.append(other_mate)
        
        # Check for conflicting mate types on same connection
        for other_mate in same_connection_mates:
            # Coincident + Distance on same reference types = conflict (either direction)
            if ((mate.mate_type == MateType.COINCIDENT and
                 other_mate.mate_type == MateType.DISTANCE) or
                (mate.mate_type == MateType.DISTANCE and
                 other_mate.mate_type == MateType.COINCIDENT)):
                conflicts.append({
                    "mate_ids": [mate.mate_id, other_mate.mate_id],
                    "type": "incompatible",
                    "description": f"Cannot have both COINCIDENT and DISTANCE "
                                   f"mates between same components",
                })
            
            # Parallel + Perpendicular on same reference types = conflict
            if ((mate.mate_type == MateType.PARALLEL and 
                 other_mate.mate_type == MateType.PERPENDICULAR) or
                (mate.mate_type == MateType.PERPENDICULAR and 
                 other_mate.mate_type == MateType.PARALLEL)):
                conflicts.append({
                    "mate_ids": [mate.mate_id, other_mate.mate_id],
                    "type": "incompatible",
                    "description": f"Cannot have both PARALLEL and PERPENDICULAR "
                                   f"mates between same components",
                })
        
        return conflicts


# Convenience functions
# =====================

def create_coincident_mate(
    manager: MateManager,
    component1_id: str,
    ref1_type: str,
    ref1_id: str,
    component2_id: str,
    ref2_type: str,
    ref2_id: str,
    name: str = ""
) -> Mate:
    """
    Convenience function to create a coincident mate.
    
    Args:
        manager: The MateManager instance
        component1_id: First component ID
        ref1_type: First reference type
        ref1_id: First reference ID
        component2_id: Second component ID
        ref2_type: Second reference type
        ref2_id: Second reference ID
        name: Optional name for the mate
        
    Returns:
        The created Mate
    """
    ref1 = MateReference(component1_id, ref1_type, ref1_id)
    ref2 = MateReference(component2_id, ref2_type, ref2_id)
    mate = manager.create_mate(MateType.COINCIDENT, ref1, ref2)
    if name:
        mate.name = name
    return mate


def create_distance_mate(
    manager: MateManager,
    component1_id: str,
    ref1_type: str,
    ref1_id: str,
    component2_id: str,
    ref2_type: str,
    ref2_id: str,
    distance: float,
    name: str = ""
) -> Mate:
    """
    Convenience function to create a distance mate.
    
    Args:
        manager: The MateManager instance
        component1_id: First component ID
        ref1_type: First reference type
        ref1_id: First reference ID
        component2_id: Second component ID
        ref2_type: Second reference type
        ref2_id: Second reference ID
        distance: The distance value
        name: Optional name for the mate
        
    Returns:
        The created Mate
    """
    ref1 = MateReference(component1_id, ref1_type, ref1_id)
    ref2 = MateReference(component2_id, ref2_type, ref2_id)
    mate = manager.create_mate(MateType.DISTANCE, ref1, ref2, distance=distance)
    if name:
        mate.name = name
    return mate
