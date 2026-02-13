
from dataclasses import dataclass, field
from typing import Tuple
import uuid

@dataclass
class ConstructionPlane:
    """
    Konstruktionsebene für Sketches auf beliebigen Z-Offsets.

    Verwendung:
    - Loft-Profile auf verschiedenen Ebenen
    - Offset von Standard-Ebenen (XY, XZ, YZ)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Plane"
    origin: Tuple[float, float, float] = (0, 0, 0)
    normal: Tuple[float, float, float] = (0, 0, 1)
    x_dir: Tuple[float, float, float] = (1, 0, 0)
    y_dir: Tuple[float, float, float] = (0, 1, 0)
    visible: bool = True

    @classmethod
    def from_offset(cls, base: str, offset: float, name: str = None):
        """
        Erstellt Ebene mit Offset von Standard-Ebene.

        Args:
            base: "XY", "XZ", oder "YZ"
            offset: Abstand in mm
            name: Optional - sonst automatisch generiert
        """
        configs = {
            "XY": ((0, 0, offset), (0, 0, 1), (1, 0, 0), (0, 1, 0)),
            "XZ": ((0, offset, 0), (0, 1, 0), (1, 0, 0), (0, 0, 1)),
            "YZ": ((offset, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
        }
        if base not in configs:
            raise ValueError(f"Base muss XY, XZ oder YZ sein, nicht {base}")

        origin, normal, x_dir, y_dir = configs[base]
        auto_name = name or f"{base} @ {offset:.1f}mm"

        return cls(
            name=auto_name,
            origin=origin,
            normal=normal,
            x_dir=x_dir,
            y_dir=y_dir
        )

    @classmethod
    def from_face(cls, face_center, face_normal, offset: float = 0.0, name: str = None):
        """
        Erstellt Ebene mit Offset von einer Körperfläche.

        Args:
            face_center: (x, y, z) Schwerpunkt der Fläche
            face_normal: (x, y, z) Normale der Fläche
            offset: Abstand in mm entlang der Normalen
            name: Optional
        """
        import numpy as np
        normal = np.array(face_normal, dtype=float)
        norm_len = np.linalg.norm(normal)
        if norm_len < 1e-12:
            raise ValueError("Flächennormale ist null")
        normal = normal / norm_len

        center = np.array(face_center, dtype=float) + normal * offset

        # x_dir orthogonal zur Normalen berechnen
        up = np.array([0, 0, 1], dtype=float)
        if abs(np.dot(normal, up)) > 0.99:
            up = np.array([1, 0, 0], dtype=float)
        x_dir = np.cross(up, normal)
        x_dir = x_dir / np.linalg.norm(x_dir)
        y_dir = np.cross(normal, x_dir)

        auto_name = name or f"Face Plane @ {offset:.1f}mm"

        return cls(
            name=auto_name,
            origin=tuple(center),
            normal=tuple(normal),
            x_dir=tuple(x_dir),
            y_dir=tuple(y_dir),
        )
