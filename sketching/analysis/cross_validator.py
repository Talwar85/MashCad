"""
Cross Validator - Vergleicht Ergebnisse aus verschiedenen Detection-Methoden
und berechnet echte Confidence basierend auf Übereinstimmung.

Author: Claude (Lead Developer)
Date: 2026-02-14
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path

import numpy as np

from .stl_feature_analyzer import HoleInfo

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Ergebnis der Cross-Validierung."""
    feature_type: str  # "base_plane", "hole", "pocket"
    feature_id: str  # Unique identifier

    # Cluster von Ergebnissen
    clustered_results: List[Dict[str, Any]] = field(default_factory=list)

    # Zusammengeführte Ergebnisse (gewichtet)
    merged_result: Optional[Any] = None

    # Metriken
    agreement_score: float = 0.0  # 0-1: Wie viele Methoden stimmen überein?
    confidence_score: float = 0.0  # Basierend auf Agreement

    # Ergebnisse pro Methode
    method_results: Dict[str, Any] = field(default_factory=dict)

    # Anzahl der Methoden die ein Ergebnis lieferten
    num_methods: int = 0
    num_successful: int = 0

    # Echte Confidence (gewichtet)
    final_confidence: float = 0.0
    detection_method: str = "cross_validated"

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dict für UI/Export."""
        return {
            "feature_type": self.feature_type,
            "feature_id": self.feature_id,
            "agreement_score": self.agreement_score,
            "confidence_score": self.confidence_score,
            "final_confidence": self.final_confidence,
            "detection_method": self.detection_method,
            "num_methods": self.num_methods,
            "num_successful": self.num_successful,
            "merged_result": self.merged_result
        }


class FeatureCrossValidator:
    """
    Vergleicht Ergebnisse aus verschiedenen Detection-Methoden
    und berechnet echte Confidence basierend auf Übereinstimmung.

    Strategien:
    1. Base Plane: Visual Projection vs. Alpha Shape vs. Slice vs. RANSAC
    2. Holes: Visual Ray-Casting vs. Edge Loop vs. Face Clustering
    """

    # Tolerances für Vergleich
    POSITION_TOLERANCE = 0.5  # mm
    ANGLE_TOLERANCE_DEG = np.radians(5.0)  # 5 Grad
    ANGLE_TOLERANCE_RAD = np.radians(15.0)  # 15 Grad für Radien
    NORMAL_THRESHOLD = 0.95  # Cosinus-Ähnlichkeit

    def __init__(self):
        """Initialisiere den Validator."""
        self.methods = {}  # Registrierte Detection-Methoden

    def register_method(self, name: str, detector_func: callable) -> None:
        """Registriert eine neue Detection-Methode."""
        self.methods[name] = detector_func
        logger.info(f"Registered detection method: {name}")

    def validate_base_plane(self, mesh, visual_result=None, alpha_result=None,
                       slice_result=None, ransac_result=None,
                       legacy_result=None) -> ValidationResult:
        """
        Validiert Base Plane Ergebnisse aus verschiedenen Methoden.

        Args:
            mesh: PyVista mesh
            visual_result: Ergebnis von VisualMeshAnalyzer
            alpha_result: Ergebnis von Alpha-Shape Methode
            slice_result: Ergebnis von Z-Slice Methode
            ransac_result: Ergebnis von RANSAC
            legacy_result: Ergebnis von 6-seitiger BB

        Returns:
            ValidationResult mit merged Base-Plane-Info
        """
        validation = ValidationResult(
            feature_type="base_plane",
            feature_id="base_plane_1",
            clustered_results=[],
            final_confidence=0.0,
            detection_method="cross_validated"
        )

        # Alle verfügbaren Methoden aufrufen
        available_methods = []
        if visual_result is not None and "visual" in self.methods:
            available_methods.append(("visual", self.methods["visual"]))
        if alpha_result is not None and "alpha_shape" in self.methods:
            available_methods.append(("alpha_shape", self.methods["alpha_shape"]))
        if slice_result is not None and "slice" in self.methods:
            available_methods.append(("slice", self.methods["slice"]))
        if ransac_result is not None and "ransac" in self.methods:
            available_methods.append(("ransac", self.methods["ransac"]))
        if legacy_result is not None and "legacy" in self.methods:
            available_methods.append(("legacy", self.methods["legacy"]))

        if not available_methods:
            logger.warning("No base plane detection results to validate")
            validation.final_confidence = 0.0
            return validation

        # Cluster nach geometrischer Ähnlichkeit
        clusters = self._cluster_by_geometry(available_methods)

        # Für jeden Cluster: konsolidiere Ergebnisse
        for cluster_id, results in clusters.items():
            if len(results) == 1:
                # Nur ein Ergebnis im Cluster
                validation.method_results[cluster_id[0]] = results[0][1]
                validation.num_methods += 1
                if results[0][1] is not None:
                    validation.num_successful += 1
            else:
                # Mehrere Ergebnisse - versuche zu mergen
                merged = self._merge_plane_results(results)
                validation.merged_result = merged
                if merged:
                    validation.num_successful += 1
                break

        # Berechne Agreement Score
        validation.agreement_score = validation.num_successful / max(1, validation.num_methods)
        validation.confidence_score = validation.agreement_score * validation.num_methods

        # Echte Confidence = Agreement * 0.7 + Basis-Confidence * 0.3
        if validation.merged_result:
            base_conf = validation.merged_result.confidence if validation.merged_result else 0
            validation.final_confidence = min(0.95, validation.confidence_score + base_conf * 0.3)

        return validation

    def validate_hole(self, mesh, visual_result=None, edge_result=None,
                face_result=None, base_plane=None) -> ValidationResult:
        """
        Validiert Hole Ergebnisse aus verschiedenen Methoden.

        Args:
            mesh: PyVista mesh
            visual_result: Ergebnis von Visual-Methode
            edge_result: Ergebnis von Edge-Loop-Methode
            face_result: Ergebnis von Face-Clustering
            base_plane: Base Plane für Referenz

        Returns:
            ValidationResult mit gemergtem HoleInfo
        """
        validation = ValidationResult(
            feature_type="hole",
            feature_id=f"hole_{np.random.randint(1000, 9999)}",
            clustered_results=[],
            final_confidence=0.0,
            detection_method="cross_validated"
        )

        # Alle verfügbaren Methoden aufrufen
        available_methods = []
        if visual_result is not None:
            available_methods.append(("visual", visual_result))
        if edge_result is not None:
            available_methods.extend([("edge", e) for e in edge_result])
        if face_result is not None:
            available_methods.extend([("face", f) for f in face_result])

        # Cluster nach Zentrum und Radius
        clusters = self._cluster_holes_by_proximity(available_methods, base_plane)

        # Für jeden Cluster: konsolidiere und validiere
        for cluster_id, results in clusters.items():
            cluster_holes = self._merge_holes_in_cluster(results)

            if cluster_holes:
                # Berechne gemittelte Parameter
                merged = self._merge_hole_parameters(cluster_holes)

                validation.clustered_results.extend([
                    {"method": m[0], "result": m[1]} for m in results.items()
                ])
                validation.num_methods = len(results)

                # Validiere Parameter
                if merged.is_valid:
                    validation.merged_result = merged
                    validation.num_successful = 1
                    break

        # Berechne Confidence
        if validation.merged_result:
            validation.final_confidence = validation.merged_result.confidence
        else:
            # Fallback: Durchschnitt der Ergebnisse
            confidences = [r.confidence for name, r in available_methods if r and hasattr(r, 'is_valid') and r.is_valid]
            validation.final_confidence = np.mean(confidences) if confidences else 0.0

        return validation

    def _cluster_by_geometry(self, available_methods: List[Tuple]) -> Dict[int, List[Tuple]]:
        """Cluster Base-Plane Ergebnisse nach geometrischer Ähnlichkeit."""
        clusters = {0: [], 1: [], 2: [], 3: []}

        # Normals und Ursprünge vergleichen
        for i, (name, result) in enumerate(available_methods):
            if result is None or result.normal is None:
                continue

            # Cluster-ID bestimmen
            cluster_id = -1
            if abs(result.normal[2]) > 0.9:  # Z-Up
                cluster_id = 0
            elif abs(result.normal[2]) < 0.1:  # Z-Down
                cluster_id = 1

            clusters[cluster_id].append((name, result))

        return clusters

    def _cluster_holes_by_proximity(self, available_methods: List[Tuple],
                                        base_plane) -> Dict[int, List[Tuple]]:
        """Cluster Hole-Ergebnisse nach räumlicher Nähe."""
        clusters = {}
        cluster_id = 0

        # Vereinfachung: Zentren näher als X mm = zusammengehörig
        proximity_threshold = 5.0  # mm

        for method_name, method_results in available_methods:
            if method_name is None:
                continue

            # Für Edge-Loops: Extrahiere jedes Loch
            if method_name == "edge":
                for hole_info in method_results[1]:
                    # Finde passenden Cluster
                    found_cluster = None
                    for cid, cluster in clusters.items():
                        for h in cluster:
                            dist = np.linalg.norm(np.array(h.center) - np.array(hole_info.center))
                            if dist < proximity_threshold:
                                found_cluster = cid
                                break
                        if found_cluster is None:
                            clusters[cluster_id] = []
                        clusters[cluster_id].append(hole_info)

            elif method_name == "face":
                # Face-Clustering Ergebnisse zu Cluster hinzufügen
                for hole_info in method_results[1]:
                    # Finde passenden Cluster
                    found_cluster = None
                    for cid, cluster in clusters.items():
                        for h in cluster:
                            dist = np.linalg.norm(np.array(h.center) - np.array(hole_info.center))
                            if dist < proximity_threshold:
                                found_cluster = cid
                                break
                    if found_cluster is None:
                        clusters[cluster_id] = []
                    clusters[cluster_id].append(hole_info)

        return clusters

    def _merge_holes_in_cluster(self, holes: List) -> Optional[HoleInfo]:
        """Vereint Hole-Parameter aus mehreren Ergebnissen."""
        if not holes:
            return None

        # Durchschnittswerte für Parameter
        centers = np.array([h.center for h in holes])
        mean_center = np.mean(centers, axis=0)
        mean_radius = np.mean([h.radius for h in holes])
        mean_depth = np.mean([h.depth for h in holes])
        mean_axis = np.mean([h.axis for h in holes], axis=0)
        mean_axis /= np.linalg.norm(mean_axis)

        # Konfidenzberechnung
        confidences = [h.confidence for h in holes]
        mean_confidence = np.mean(confidences)

        # Normalisierung der Achse (für Aufsummung)
        if np.dot(mean_axis, mean_axis) < 0:
            mean_axis = -mean_axis

        return HoleInfo(
            center=tuple(mean_center),
            radius=float(mean_radius),
            depth=float(mean_depth),
            axis=tuple(mean_axis),
            confidence=float(mean_confidence),
            detection_method=f"cross_validated_merge_{len(holes)}",
            face_indices=list(set().union(*[h.face_indices for h in holes])),
        )

    def _merge_hole_parameters(self, holes: List) -> Optional[HoleInfo]:
        """Vereint Hole-Parameter mit Gewicht-basierter Priorität."""
        if not holes:
            return None

        # Zentren: Radius gewichtet höher als Tiefe (mehr Konfidenz)
        best_hole = max(holes, key=lambda h: h.radius * h.confidence)

        # Tiefe: gewichte durchschnittliche Tiefe, aber höhere Konfidenz bevorzugt
        depth_candidates = [h for h in holes if h.depth > 0]
        if depth_candidates:
            avg_depth = np.mean([h.depth for h in depth_candidates])
            # Gewichte: Durchschnittliche Tiefe mit Konfidenz-Gewichtung
            weighted_depth = avg_depth * 0.7 + best_hole.depth * 0.3
        else:
            # Fallback: Radius * 2
            weighted_depth = best_hole.radius * 2

        # Parameter des besten Lochs
        params = []
        for h in holes:
            if h == best_hole:
                params.append(h)
            elif h.depth > 0:
                # Tiefe anpassen
                h_with_depth = HoleInfo(
                    center=h.center,
                    radius=h.radius,
                    depth=weighted_depth,
                    axis=h.axis,
                    confidence=h.confidence * 0.9,  # Reduziert wegen Tiefe-Schätzung
                    detection_method=f"{h.detection_method}_depth_adjusted"
                )
                params.append(h_with_depth)
            else:
                params.append(h)

        # Zentren nach Parameter-ähnlichkeit
        # Prefer: (1) Höchste Konfidenz, (2) Richtigste Tiefe
        params.sort(key=lambda h: (h.confidence, h.depth), reverse=True)

        return params[0]  # Bestes Ergebnis

    def validate_pockets(self, mesh, visual_result=None, legacy_result=None) -> ValidationResult:
        """Validiert Pocket-Ergebnisse (derzeit nur eine Methode verfügbar)."""
        validation = ValidationResult(
            feature_type="pocket",
            feature_id=f"pocket_{np.random.randint(1000, 9999)}",
            clustered_results=[],
            final_confidence=0.0,
            detection_method="cross_validated"
        )

        if visual_result:
            validation.method_results["visual"] = visual_result
            validation.num_methods += 1
            if visual_result:
                validation.num_successful += 1
                validation.merged_result = visual_result
                validation.final_confidence = visual_result.confidence
                return validation

        if legacy_result:
            validation.method_results["legacy"] = legacy_result
            validation.num_methods += 1
            if legacy_result:
                validation.num_successful += 1
                validation.merged_result = legacy_result

        return validation

    def validate_stl_analysis(self, analysis_results: Dict[str, Any],
                          mesh=None) -> Dict[str, ValidationResult]:
        """
        Führt komplette STL-Analyse aus.

        Args:
            analysis_results: Dict mit Ergebnissen von allen Methoden
            mesh: Optional PyVista mesh (für Cross-Check)

        Returns:
            Dict mit ValidationResult für jedes Feature
        """
        results = {}

        # Base Plane validieren
        if "base_plane" in analysis_results:
            results["base_plane"] = self.validate_base_plane(
                mesh,
                visual_result=analysis_results.get("visual_base_plane"),
                alpha_result=analysis_results.get("alpha_base_plane"),
                slice_result=analysis_results.get("slice_base_plane"),
                ransac_result=analysis_results.get("ransac_base_plane"),
                legacy_result=analysis_results.get("legacy_base_plane")
            )

        # Löcher validieren
        holes_data = [(k, v) for k, v in analysis_results.items() if "hole" in k.lower()]
        for method_name, hole_list in holes_data:
            for i, h in enumerate(hole_list):
                if i == 0:
                    results[f"hole_{i}"] = h
                else:
                    results[f"hole_{i}"] = h

        if results:
            # Hole-Validierung
            edge_results = results.get("hole_0", [])
            face_results = results.get("hole_1", [])

            validation = self.validate_hole(
                mesh,
                visual_result=results.get("visual_hole"),
                edge_result=edge_results if edge_results else None,
                face_result=face_results if face_results else None,
                base_plane=analysis_results.get("base_plane")
            )

            # Erste Hole-FEATURE-ID für Ergebnisse
            final_hole_id = f"hole_validated"
            if validation.merged_result:
                validation.merged_result.feature_id = final_hole_id
                validation.merged_result.detection_method = f"cross_validated"

            results["holes"] = validation

        return results


# Convenience Functions
def cross_validate_stl(visual_result: Any = None,
                     alpha_shape_result: Any = None,
                     slice_result: Any = None,
                     ransac_result: Any = None,
                     legacy_result: Any = None) -> Dict[str, ValidationResult]:
    """
    Führt Cross-Validation für STL-Ergebnisse.

    Args:
        visual_result: Ergebnis von VisualMeshAnalyzer
        alpha_shape_result: Ergebnis von Alpha-Shape Methode
        slice_result: Ergebnis von Z-Slice Methode
        ransac_result: Ergebnis von RANSAC
        legacy_result: Ergebnis von 6-seitigem BB

    Returns:
        Dict mit ValidationResult für base_plane und holes
    """
    validator = FeatureCrossValidator()

    return validator.validate_stl_analysis({
        "visual_base_plane": visual_result,
        "alpha_base_plane": alpha_shape_result,
        "slice_base_plane": slice_result,
        "ransac_base_plane": ransac_result,
        "legacy_base_plane": legacy_result,
        "visual_hole": visual_result,
        "hole_0": [],  # Placeholder for edge_loop_result
        "hole_1": [],  # Placeholder for face_clustering_result
    })
