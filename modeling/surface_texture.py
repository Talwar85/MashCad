"""
Surface Texture Feature - Non-destruktive Flächen-Texturierung für 3D-Druck.

KRITISCH: Das BREP wird NIEMALS modifiziert. Texturen sind ein reiner Metadaten-Layer.
Die Textur wird erst beim Export als Displacement auf das tessellierte Mesh angewendet.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from enum import Enum, auto
import numpy as np

from loguru import logger


class TextureType(Enum):
    """Verfügbare Textur-Typen für 3D-Druck."""
    RIPPLE = "ripple"           # Grip-Rillen (Wellen)
    HONEYCOMB = "honeycomb"     # Wabenstruktur (Leichtbau)
    DIAMOND = "diamond"         # Rauten-Muster (Grip)
    KNURL = "knurl"             # Rändelmuster (Griffe)
    CROSSHATCH = "crosshatch"   # Kreuzschraffur (Anti-Rutsch)
    VORONOI = "voronoi"         # Organische Zellstruktur
    CUSTOM = "custom"           # Benutzerdefinierte Heightmap


# Default-Parameter für jeden Textur-Typ
TEXTURE_DEFAULTS = {
    TextureType.RIPPLE: {
        "wave_count": 5,
        "wave_shape": "sine",  # sine, triangle, square
        "print_safe": True,    # 3D-Druck-Optimierung (keine Überhänge >45°)
    },
    TextureType.HONEYCOMB: {
        "cell_size": 3.0,      # mm
        "wall_thickness": 0.5,  # mm
    },
    TextureType.DIAMOND: {
        "aspect_ratio": 1.0,
        "pyramid_height": 0.3,  # Relative Höhe
    },
    TextureType.KNURL: {
        "pitch": 1.0,          # mm
        "angle": 30.0,         # Grad
    },
    TextureType.CROSSHATCH: {
        "line_spacing": 1.0,   # mm
        "line_depth": 0.3,     # Relative Tiefe
    },
    TextureType.VORONOI: {
        "cell_count": 20,
        "randomness": 0.5,     # 0-1
        "edge_width": 0.3,     # Relative Kantenbreite
        "seed": 42,            # Für Reproduzierbarkeit
    },
    TextureType.CUSTOM: {
        "heightmap_path": "",
    },
}


class TextureGenerator:
    """
    Generiert Height-Maps für verschiedene Textur-Typen.

    Height-Maps sind 2D-Arrays mit Werten 0-1, die später als
    Displacement entlang der Face-Normalen angewendet werden.
    """

    @staticmethod
    def generate(texture_type: str, params: dict, size: int = 256) -> np.ndarray:
        """
        Generiert Height-Map für gegebenen Textur-Typ.

        Args:
            texture_type: TextureType value als String
            params: Typ-spezifische Parameter
            size: Auflösung der Height-Map (size x size)

        Returns:
            np.ndarray mit Shape (size, size), Werte 0-1
        """
        # Koordinaten-Grid erstellen
        x = np.linspace(0, 1, size)
        y = np.linspace(0, 1, size)
        X, Y = np.meshgrid(x, y)

        if texture_type == "ripple":
            return TextureGenerator._ripple(X, Y, params)
        elif texture_type == "honeycomb":
            return TextureGenerator._honeycomb(X, Y, params)
        elif texture_type == "diamond":
            return TextureGenerator._diamond(X, Y, params)
        elif texture_type == "knurl":
            return TextureGenerator._knurl(X, Y, params)
        elif texture_type == "crosshatch":
            return TextureGenerator._crosshatch(X, Y, params)
        elif texture_type == "voronoi":
            return TextureGenerator._voronoi(size, params)
        elif texture_type == "custom":
            return TextureGenerator._custom(params, size)
        else:
            logger.warning(f"Unbekannter Textur-Typ: {texture_type}, verwende flache Oberfläche")
            return np.zeros((size, size))

    @staticmethod
    def _ripple(X: np.ndarray, Y: np.ndarray, params: dict) -> np.ndarray:
        """
        Wellenförmige Rillen.

        Bei print_safe=True wird das Profil 3D-Druck-konform:
        - Nur positive Displacement (kein Einschneiden in den Körper)
        - Mindest-Basishöhe (20%) damit nichts frei schwebt
        - Überhangwinkel auf max ~45° begrenzt
        - Alle Formen behalten Verbindung zur Oberfläche
        """
        wave_count = params.get("wave_count", 5)
        wave_shape = params.get("wave_shape", "sine")
        print_safe = params.get("print_safe", True)

        phase = X * wave_count * 2 * np.pi

        if wave_shape == "sine":
            height = np.sin(phase) * 0.5 + 0.5

            if print_safe:
                # Sine-Welle abflachen: Überhänge begrenzen
                # Raised-Cosine-Profil ist sanfter als reiner Sinus
                height = 0.5 * (1.0 - np.cos(phase)) * 0.5 + 0.25
                height = np.clip(height, 0.0, 1.0)
                height = (height - height.min()) / (height.max() - height.min() + 1e-10)

        elif wave_shape == "triangle":
            t = phase / (2 * np.pi) % 1
            height = np.abs(2 * t - 1)

            if print_safe:
                flat_zone = 0.15
                height = np.clip(height, flat_zone, 1.0 - flat_zone)
                height = (height - flat_zone) / (1.0 - 2 * flat_zone)

        elif wave_shape == "square":
            height = (np.sin(phase) > 0).astype(float)

            if print_safe:
                steepness = 10.0
                height = 1.0 / (1.0 + np.exp(-steepness * np.sin(phase)))
        else:
            height = np.sin(phase) * 0.5 + 0.5

        if print_safe:
            base_height = 0.2
            height = base_height + height * (1.0 - base_height)

        return height

    @staticmethod
    def _honeycomb(X: np.ndarray, Y: np.ndarray, params: dict) -> np.ndarray:
        """Hexagonale Wabenstruktur."""
        cell_size = params.get("cell_size", 3.0)
        wall_thickness = params.get("wall_thickness", 0.5)

        # Hexagon-Geometrie
        # Skaliere auf Pattern-Raum
        scale = 1.0 / (cell_size / 10.0)  # Normalisiert auf ~10 Zellen
        Xs = X * scale
        Ys = Y * scale

        # Offset für gerade/ungerade Reihen
        row = np.floor(Ys * 2 / np.sqrt(3))
        offset = (row % 2) * 0.5

        # Nächstes Zellzentrum finden
        col = np.floor(Xs + offset)
        cx = col - offset + 0.5
        cy = (row + 0.5) * np.sqrt(3) / 2

        # Distanz zum Zentrum
        dx = Xs - cx
        dy = Ys - cy
        dist = np.sqrt(dx**2 + dy**2)

        # Hexagon-Approximation mit Kreis
        cell_radius = 0.5 - (wall_thickness / cell_size * 0.5)

        # Inneres = tief (0), Wände = hoch (1)
        height = np.clip((dist - cell_radius) / (wall_thickness / cell_size), 0, 1)

        return height

    @staticmethod
    def _diamond(X: np.ndarray, Y: np.ndarray, params: dict) -> np.ndarray:
        """Rauten/Diamant-Muster."""
        aspect = params.get("aspect_ratio", 1.0)

        # Diagonale Koordinaten
        u = (X + Y * aspect) % 1
        v = (X - Y * aspect) % 1

        # Pyramidenförmige Erhöhungen
        height = 1 - 2 * np.maximum(np.abs(u - 0.5), np.abs(v - 0.5))
        height = np.clip(height, 0, 1)

        return height

    @staticmethod
    def _knurl(X: np.ndarray, Y: np.ndarray, params: dict) -> np.ndarray:
        """Rändelmuster (gekreuzte Diagonalen)."""
        pitch = params.get("pitch", 1.0)
        angle = np.radians(params.get("angle", 30))

        # Zwei Richtungen
        scale = 10.0 / pitch

        # Diagonale 1
        d1 = X * np.cos(angle) + Y * np.sin(angle)
        pattern1 = np.sin(d1 * scale * 2 * np.pi) * 0.5 + 0.5

        # Diagonale 2 (gegenläufig)
        d2 = X * np.cos(-angle) + Y * np.sin(-angle)
        pattern2 = np.sin(d2 * scale * 2 * np.pi) * 0.5 + 0.5

        # Kombinieren: Minimum ergibt Knurl-Muster
        height = np.minimum(pattern1, pattern2)

        return height

    @staticmethod
    def _crosshatch(X: np.ndarray, Y: np.ndarray, params: dict) -> np.ndarray:
        """Kreuzschraffur."""
        spacing = params.get("line_spacing", 1.0)

        scale = 10.0 / spacing

        # Horizontale und vertikale Linien
        h_lines = np.abs(np.sin(Y * scale * np.pi))
        v_lines = np.abs(np.sin(X * scale * np.pi))

        # Kombinieren: Minimum ergibt Kreuzung
        height = np.minimum(h_lines, v_lines)

        return height

    @staticmethod
    def _voronoi(size: int, params: dict) -> np.ndarray:
        """Organische Voronoi-Zellstruktur."""
        try:
            from scipy.spatial import Voronoi
            from scipy.ndimage import distance_transform_edt
        except ImportError:
            logger.warning("scipy nicht verfügbar, verwende Fallback für Voronoi")
            return np.zeros((size, size))

        cell_count = params.get("cell_count", 20)
        randomness = params.get("randomness", 0.5)
        edge_width = params.get("edge_width", 0.3)
        seed = params.get("seed", 42)

        np.random.seed(seed)

        # Zufällige Punkte generieren
        points = np.random.rand(cell_count, 2)

        # Punkte etwas gleichmäßiger verteilen wenn randomness < 1
        if randomness < 1.0:
            # Grid-basierte Initialisierung mit Jitter
            grid_size = int(np.sqrt(cell_count))
            grid_x, grid_y = np.meshgrid(
                np.linspace(0.1, 0.9, grid_size),
                np.linspace(0.1, 0.9, grid_size)
            )
            grid_points = np.column_stack([grid_x.ravel(), grid_y.ravel()])

            # Interpolieren zwischen Grid und Random
            n = min(len(grid_points), cell_count)
            points[:n] = (1 - randomness) * grid_points[:n] + randomness * points[:n]

        # Pixel-Grid erstellen
        x = np.linspace(0, 1, size)
        y = np.linspace(0, 1, size)
        X, Y = np.meshgrid(x, y)
        positions = np.column_stack([X.ravel(), Y.ravel()])

        # Distanz zu nächstem Punkt berechnen
        from scipy.spatial import cKDTree
        tree = cKDTree(points)
        distances, _ = tree.query(positions)
        distances = distances.reshape(size, size)

        # Zweite nächste Distanz für Kanten
        distances2, _ = tree.query(positions, k=2)
        edge_dist = (distances2[:, 1] - distances2[:, 0]).reshape(size, size)

        # Kanten = wo Differenz klein ist
        edge_threshold = edge_width * 0.1
        height = 1.0 - np.clip(edge_dist / edge_threshold, 0, 1)

        return height

    @staticmethod
    def _custom(params: dict, size: int) -> np.ndarray:
        """Lädt benutzerdefinierte Heightmap aus Bilddatei."""
        path = params.get("heightmap_path", "")

        if not path:
            logger.warning("Kein Heightmap-Pfad angegeben")
            return np.zeros((size, size))

        try:
            from PIL import Image

            img = Image.open(path).convert('L')  # Graustufen
            try:
                resampling = Image.Resampling.BILINEAR
            except AttributeError:
                resampling = Image.BILINEAR  # Fallback für ältere Pillow Versionen
            img = img.resize((size, size), resampling)
            height = np.array(img, dtype=np.float32) / 255.0

            return height

        except ImportError:
            logger.error("PIL/Pillow nicht installiert für Custom Heightmap")
            return np.zeros((size, size))
        except Exception as e:
            logger.error(f"Fehler beim Laden der Heightmap '{path}': {e}")
            return np.zeros((size, size))


def sample_heightmap_at_uvs(
    heightmap: np.ndarray,
    uvs: np.ndarray,
    scale: float = 1.0,
    rotation: float = 0.0
) -> np.ndarray:
    """
    Sampelt Heightmap an gegebenen UV-Koordinaten.

    Args:
        heightmap: 2D Height-Map Array (size x size)
        uvs: UV-Koordinaten Array (N, 2) in mm
        scale: Pattern-Skalierung in mm
        rotation: Pattern-Rotation in Grad

    Returns:
        Height-Werte Array (N,) mit Werten 0-1
    """
    # Rotation anwenden
    angle = np.radians(rotation)
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    u_rot = uvs[:, 0] * cos_a - uvs[:, 1] * sin_a
    v_rot = uvs[:, 0] * sin_a + uvs[:, 1] * cos_a

    # Skalieren auf Pattern-Raum (0-1)
    u_scaled = (u_rot / scale) % 1.0
    v_scaled = (v_rot / scale) % 1.0

    # In Pixel-Koordinaten umrechnen
    size = heightmap.shape[0]
    px = (u_scaled * (size - 1)).astype(int)
    py = (v_scaled * (size - 1)).astype(int)

    # Clampen
    px = np.clip(px, 0, size - 1)
    py = np.clip(py, 0, size - 1)

    # Sampeln
    return heightmap[py, px]
