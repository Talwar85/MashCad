"""
Machine Learning basierte Primitiv-Erkennung.

Verwendet ein neuronales Netz um Mesh-Faces zu klassifizieren:
- PLANE (planare Fläche)
- CYLINDER (zylindrische Fläche)
- SPHERE (sphärische Fläche)
- OTHER (Freiform)

Features pro Face:
- Normalen (3D)
- Curvature (Gaußsche und mittlere Krümmung)
- Nachbar-Normalen-Varianz
- Face-Fläche

Training:
- Synthetische Daten (generierte Primitive)
- Oder echte annotierte Meshes
"""

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import numpy as np
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from enum import IntEnum
from loguru import logger

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.utils.data import Dataset, DataLoader
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.warning("PyTorch nicht verfügbar")

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False


class PrimitiveType(IntEnum):
    """Primitiv-Typen für Klassifikation."""
    PLANE = 0
    CYLINDER = 1
    SPHERE = 2
    OTHER = 3


@dataclass
class MLDetectionResult:
    """Ergebnis der ML-Erkennung."""
    face_labels: np.ndarray  # Label pro Face
    face_probabilities: np.ndarray  # Wahrscheinlichkeiten [N, 4]
    regions: Dict[PrimitiveType, List[List[int]]]  # Gruppierte Face-Indices


class PrimitiveClassifier(nn.Module):
    """
    Neuronales Netz für Face-Klassifikation.

    Input: Feature-Vektor pro Face
    Output: Wahrscheinlichkeit für jeden Primitiv-Typ
    """

    def __init__(self, input_dim: int = 12, hidden_dim: int = 64, num_classes: int = 4):
        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.BatchNorm1d(hidden_dim),
            nn.Dropout(0.2),

            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.BatchNorm1d(hidden_dim),
            nn.Dropout(0.2),

            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),

            nn.Linear(hidden_dim // 2, num_classes)
        )

    def forward(self, x):
        return self.network(x)


class MeshFeatureExtractor:
    """
    Extrahiert Features aus Mesh-Faces für ML.

    Features (12D):
    - Normal (3D)
    - Centroid (3D) - normalisiert
    - Nachbar-Normalen-Statistik (3D): mean, std, max_angle
    - Geometrie (3D): area, aspect_ratio, curvature_estimate
    """

    def __init__(self):
        pass

    def extract(self, mesh: 'pv.PolyData') -> np.ndarray:
        """
        Extrahiert Features für alle Faces.

        Returns:
            np.ndarray mit Shape [N_faces, 12]
        """
        # Stelle sicher dass Normalen vorhanden sind
        if 'Normals' not in mesh.cell_data:
            mesh.compute_normals(cell_normals=True, inplace=True)

        normals = mesh.cell_data['Normals']
        n_faces = mesh.n_cells
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = mesh.points

        # Baue Adjacency
        adjacency = self._build_adjacency(mesh)

        features = np.zeros((n_faces, 12), dtype=np.float32)

        # Berechne Mesh-Bounds für Normalisierung
        bounds = mesh.bounds
        scale = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])
        center = np.array([(bounds[0] + bounds[1]) / 2,
                           (bounds[2] + bounds[3]) / 2,
                           (bounds[4] + bounds[5]) / 2])

        for i in range(n_faces):
            # 1. Normal (3D)
            features[i, 0:3] = normals[i]

            # 2. Centroid normalisiert (3D)
            v0, v1, v2 = faces[i]
            centroid = (points[v0] + points[v1] + points[v2]) / 3
            centroid_norm = (centroid - center) / (scale + 1e-6)
            features[i, 3:6] = centroid_norm

            # 3. Nachbar-Normalen-Statistik (3D)
            neighbors = adjacency.get(i, [])
            if neighbors:
                neighbor_normals = normals[neighbors]
                # Mittlere Abweichung
                mean_dot = np.mean([np.dot(normals[i], n) for n in neighbor_normals])
                # Std der Normalen
                std_normal = np.std(neighbor_normals)
                # Max Winkel
                dots = [np.dot(normals[i], n) for n in neighbor_normals]
                max_angle = np.arccos(np.clip(min(dots), -1, 1))
                features[i, 6] = mean_dot
                features[i, 7] = std_normal
                features[i, 8] = max_angle
            else:
                features[i, 6:9] = [1.0, 0.0, 0.0]

            # 4. Geometrie (3D)
            # Face-Fläche
            e1 = points[v1] - points[v0]
            e2 = points[v2] - points[v0]
            area = 0.5 * np.linalg.norm(np.cross(e1, e2))
            features[i, 9] = np.log(area + 1e-10) / 10  # Log-Scale, normalisiert

            # Aspect Ratio
            edge_lengths = [
                np.linalg.norm(points[v1] - points[v0]),
                np.linalg.norm(points[v2] - points[v1]),
                np.linalg.norm(points[v0] - points[v2])
            ]
            max_edge = max(edge_lengths)
            min_edge = min(edge_lengths)
            aspect = min_edge / (max_edge + 1e-10)
            features[i, 10] = aspect

            # Curvature Estimate (basierend auf Nachbar-Winkel)
            if neighbors:
                # Einfache Krümmungsschätzung: Varianz der Nachbar-Normalen
                curvature = 1.0 - mean_dot  # Hohe Varianz = hohe Krümmung
                features[i, 11] = curvature
            else:
                features[i, 11] = 0.0

        return features

    def _build_adjacency(self, mesh: 'pv.PolyData') -> Dict[int, List[int]]:
        """Baut Face-Adjacency basierend auf gemeinsamen Kanten."""
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        n_faces = len(faces)

        # Edge zu Faces Mapping
        edge_to_faces = {}
        for f_idx, face in enumerate(faces):
            for i in range(3):
                v1, v2 = int(face[i]), int(face[(i + 1) % 3])
                edge = (min(v1, v2), max(v1, v2))
                if edge not in edge_to_faces:
                    edge_to_faces[edge] = []
                edge_to_faces[edge].append(f_idx)

        # Adjacency
        adjacency = {i: [] for i in range(n_faces)}
        for edge, face_list in edge_to_faces.items():
            if len(face_list) == 2:
                f1, f2 = face_list
                if f2 not in adjacency[f1]:
                    adjacency[f1].append(f2)
                if f1 not in adjacency[f2]:
                    adjacency[f2].append(f1)

        return adjacency


class SyntheticDataGenerator:
    """
    Generiert synthetische Trainings-Daten.

    Erstellt Meshes von bekannten Primitiven mit Labels.
    """

    def __init__(self, noise_level: float = 0.01):
        self.noise = noise_level

    def generate_plane_mesh(self, n_points: int = 100) -> Tuple['pv.PolyData', np.ndarray]:
        """Generiert planares Mesh."""
        # Grid
        x = np.linspace(0, 10, int(np.sqrt(n_points)))
        y = np.linspace(0, 10, int(np.sqrt(n_points)))
        xx, yy = np.meshgrid(x, y)
        zz = np.zeros_like(xx) + np.random.randn(*xx.shape) * self.noise

        points = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])
        mesh = pv.PolyData(points).delaunay_2d()

        labels = np.full(mesh.n_cells, PrimitiveType.PLANE, dtype=np.int64)
        return mesh, labels

    def generate_cylinder_mesh(self, radius: float = 2.0, height: float = 10.0,
                                n_theta: int = 32, n_z: int = 10) -> Tuple['pv.PolyData', np.ndarray]:
        """Generiert zylindrisches Mesh."""
        theta = np.linspace(0, 2 * np.pi, n_theta, endpoint=False)
        z = np.linspace(0, height, n_z)
        tt, zz = np.meshgrid(theta, z)

        r = radius + np.random.randn(*tt.shape) * self.noise
        xx = r * np.cos(tt)
        yy = r * np.sin(tt)

        points = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])
        mesh = pv.PolyData(points).delaunay_2d()

        labels = np.full(mesh.n_cells, PrimitiveType.CYLINDER, dtype=np.int64)
        return mesh, labels

    def generate_sphere_mesh(self, radius: float = 5.0, n_points: int = 500) -> Tuple['pv.PolyData', np.ndarray]:
        """Generiert sphärisches Mesh."""
        # Fibonacci-Sampling für gleichmäßige Verteilung
        indices = np.arange(n_points) + 0.5
        phi = np.arccos(1 - 2 * indices / n_points)
        theta = np.pi * (1 + np.sqrt(5)) * indices

        r = radius + np.random.randn(n_points) * self.noise
        x = r * np.sin(phi) * np.cos(theta)
        y = r * np.sin(phi) * np.sin(theta)
        z = r * np.cos(phi)

        points = np.column_stack([x, y, z])
        mesh = pv.PolyData(points).delaunay_2d()

        labels = np.full(mesh.n_cells, PrimitiveType.SPHERE, dtype=np.int64)
        return mesh, labels

    def generate_training_batch(self, batch_size: int = 100) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generiert einen Batch von Trainings-Daten.

        Returns:
            Tuple von (features [N, 12], labels [N])
        """
        all_features = []
        all_labels = []

        extractor = MeshFeatureExtractor()

        for _ in range(batch_size):
            prim_type = np.random.choice([0, 1, 2])  # Plane, Cylinder, Sphere

            if prim_type == 0:
                mesh, labels = self.generate_plane_mesh()
            elif prim_type == 1:
                mesh, labels = self.generate_cylinder_mesh()
            else:
                mesh, labels = self.generate_sphere_mesh()

            features = extractor.extract(mesh)
            all_features.append(features)
            all_labels.append(labels)

        return np.vstack(all_features), np.concatenate(all_labels)


class MLPrimitiveDetector:
    """
    ML-basierter Primitiv-Detektor.

    Verwendet ein trainiertes Modell zur Face-Klassifikation.
    """

    def __init__(self, model_path: Optional[str] = None):
        if not HAS_TORCH:
            raise ImportError("PyTorch required")

        self.model = PrimitiveClassifier()
        self.extractor = MeshFeatureExtractor()

        if model_path and os.path.exists(model_path):
            self.load_model(model_path)
            logger.info(f"Modell geladen: {model_path}")
        else:
            logger.info("Kein Modell geladen - Training erforderlich")

    def train(self, epochs: int = 100, batch_size: int = 32, lr: float = 0.001):
        """Trainiert das Modell auf synthetischen Daten."""
        logger.info("Trainiere ML-Modell auf synthetischen Daten...")

        generator = SyntheticDataGenerator(noise_level=0.02)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = nn.CrossEntropyLoss()

        self.model.train()

        for epoch in range(epochs):
            # Generiere Trainings-Batch
            features, labels = generator.generate_training_batch(batch_size)

            # Zu Tensoren
            x = torch.FloatTensor(features)
            y = torch.LongTensor(labels)

            # Forward
            optimizer.zero_grad()
            outputs = self.model(x)
            loss = criterion(outputs, y)

            # Backward
            loss.backward()
            optimizer.step()

            if (epoch + 1) % 20 == 0:
                # Accuracy
                with torch.no_grad():
                    preds = torch.argmax(outputs, dim=1)
                    acc = (preds == y).float().mean().item()
                logger.info(f"Epoch {epoch+1}/{epochs}, Loss: {loss.item():.4f}, Acc: {acc:.3f}")

        logger.success("Training abgeschlossen")

    def detect(self, mesh: 'pv.PolyData') -> MLDetectionResult:
        """
        Klassifiziert alle Faces im Mesh.

        Returns:
            MLDetectionResult mit Labels und Wahrscheinlichkeiten
        """
        self.model.eval()

        # Features extrahieren
        features = self.extractor.extract(mesh)
        x = torch.FloatTensor(features)

        # Inferenz
        with torch.no_grad():
            outputs = self.model(x)
            probs = F.softmax(outputs, dim=1).numpy()
            labels = np.argmax(probs, axis=1)

        # Gruppiere zu Regionen (zusammenhängende Faces mit gleichem Label)
        regions = self._group_to_regions(mesh, labels)

        return MLDetectionResult(
            face_labels=labels,
            face_probabilities=probs,
            regions=regions
        )

    def _group_to_regions(self, mesh: 'pv.PolyData', labels: np.ndarray) -> Dict[PrimitiveType, List[List[int]]]:
        """Gruppiert Faces mit gleichem Label zu zusammenhängenden Regionen."""
        adjacency = self.extractor._build_adjacency(mesh)
        visited = set()
        regions = {pt: [] for pt in PrimitiveType}

        for start_idx in range(len(labels)):
            if start_idx in visited:
                continue

            label = labels[start_idx]
            region = []
            queue = [start_idx]

            while queue:
                idx = queue.pop(0)
                if idx in visited:
                    continue
                if labels[idx] != label:
                    continue

                visited.add(idx)
                region.append(idx)

                for neighbor in adjacency.get(idx, []):
                    if neighbor not in visited:
                        queue.append(neighbor)

            if region:
                regions[PrimitiveType(label)].append(region)

        return regions

    def save_model(self, path: str):
        """Speichert das Modell."""
        torch.save(self.model.state_dict(), path)
        logger.info(f"Modell gespeichert: {path}")

    def load_model(self, path: str):
        """Lädt das Modell."""
        self.model.load_state_dict(torch.load(path, weights_only=True))
        self.model.eval()


def train_and_save_model(output_path: str = "models/primitive_classifier.pth",
                          epochs: int = 200):
    """Trainiert und speichert ein neues Modell."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    detector = MLPrimitiveDetector()
    detector.train(epochs=epochs, batch_size=50)
    detector.save_model(output_path)

    return detector
