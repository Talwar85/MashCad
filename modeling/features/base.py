
from enum import Enum, auto
from dataclasses import dataclass, field
import uuid
from typing import Optional, List

class FeatureType(Enum):
    SKETCH = auto()
    EXTRUDE = auto()
    REVOLVE = auto()
    FILLET = auto()
    CHAMFER = auto()
    TRANSFORM = auto()  # Für Move/Rotate/Scale/Mirror
    BOOLEAN = auto()    # Boolean-Operationen (Join, Cut, Common/Intersect)
    PUSHPULL = auto()   # Push/Pull auf Faces (Extrusion von existierenden Flächen)
    PATTERN = auto()    # Pattern (Linear, Circular, Mirror)
    LOFT = auto()       # Phase 6: Loft zwischen Profilen
    SWEEP = auto()      # Phase 6: Sweep entlang Pfad
    SHELL = auto()      # Phase 6: Körper aushöhlen
    SURFACE_TEXTURE = auto()  # Phase 7: Flächen-Texturierung für 3D-Druck
    HOLE = auto()             # Bohrung (Simple, Counterbore, Countersink)
    DRAFT = auto()            # Entformungsschräge
    SPLIT = auto()            # Körper teilen
    THREAD = auto()           # Gewinde (kosmetisch + geometrisch)
    HOLLOW = auto()           # Aushöhlen mit optionalem Drain Hole
    LATTICE = auto()          # Gitterstruktur für Leichtbau
    NSIDED_PATCH = auto()     # N-seitiger Patch (Surface Fill)
    PRIMITIVE = auto()        # Primitive (Box, Cylinder, Sphere, Cone)
    IMPORT = auto()           # Importierter Body (Mesh-Konvertierung, STEP Import)
    CADQUERY = auto()         # CadQuery/Build123d Script (editable parametric feature)

@dataclass
class Feature:
    type: FeatureType = None
    name: str = "Feature"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    visible: bool = True
    suppressed: bool = False
    status: str = "OK" # OK, ERROR, WARNING
    status_message: str = ""
    # Structured status payload for UI/diagnostics (code, refs, hints).
    status_details: dict = field(default_factory=dict)
