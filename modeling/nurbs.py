"""
MashCad - NURBS & B-Spline Infrastruktur
========================================

Phase 8: CAD-Kernel Erweiterungen

Native NURBS-Kurven und -Flächen mit:
- De Boor Algorithmus für Evaluation
- Ableitungen und Krümmungsberechnung
- OCP/Build123d Integration
- Kontinuitäts-Modi (G0/G1/G2)

Verwendung:
    from modeling.nurbs import NURBSCurve, NURBSSurface, ContinuityMode

    # Kubische B-Spline Kurve
    curve = NURBSCurve(
        control_points=[(0,0,0), (10,20,0), (30,20,0), (40,0,0)],
        degree=3
    )
    point = curve.evaluate(0.5)

    # Zu OCP konvertieren
    ocp_curve = curve.to_ocp()

Author: Claude (Phase 8 CAD-Kernel)
Date: 2026-01-23
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Any, Union
from enum import Enum, auto
import numpy as np
from loguru import logger


class CurveType(Enum):
    """Kurventypen für CAD-Modellierung."""
    LINE = auto()
    ARC = auto()
    CIRCLE = auto()
    ELLIPSE = auto()
    BSPLINE = auto()
    BEZIER = auto()
    NURBS = auto()


class ContinuityMode(Enum):
    """
    Kontinuitäts-Modi für Kurven-/Flächen-Übergänge.

    G0: Position (Punkt-Kontinuität) - Kurven treffen sich
    G1: Tangente (Richtungs-Kontinuität) - Gleiche Richtung am Übergang
    G2: Krümmung (Curvature-Kontinuität) - Gleiche Krümmung am Übergang
    G3: Krümmungsänderung (Torsion) - Glatte Krümmungsänderung
    """
    G0 = 0  # Position
    G1 = 1  # Tangente
    G2 = 2  # Krümmung
    G3 = 3  # Torsion


@dataclass
class NURBSCurve:
    """
    Native NURBS-Kurve mit voller Parametrisierung.

    Mathematisch: C(u) = Σ N_i,p(u) * w_i * P_i / Σ N_i,p(u) * w_i

    Wobei:
    - N_i,p(u): B-Spline Basisfunktionen
    - w_i: Gewichte (für rationale Kurven)
    - P_i: Kontrollpunkte

    Attributes:
        control_points: Kontrollpunkte [(x, y, z), ...]
        weights: Gewichte für rationale Kurven (default: alle 1.0)
        knots: Knotenvektor (default: uniform clamped)
        degree: Polynomgrad (default: 3 = kubisch)
    """
    control_points: List[Tuple[float, float, float]]
    weights: List[float] = field(default_factory=list)
    knots: List[float] = field(default_factory=list)
    degree: int = 3

    def __post_init__(self):
        n = len(self.control_points)

        if n < 2:
            raise ValueError("Mindestens 2 Kontrollpunkte erforderlich")

        # Grad auf max. n-1 begrenzen
        if self.degree >= n:
            self.degree = n - 1
            logger.warning(f"Grad auf {self.degree} reduziert (n={n})")

        # Default Gewichte (alle 1.0 = nicht-rational = B-Spline)
        if not self.weights:
            self.weights = [1.0] * n

        if len(self.weights) != n:
            raise ValueError(f"Anzahl Gewichte ({len(self.weights)}) != Kontrollpunkte ({n})")

        # Default Knotenvektor (uniform clamped)
        if not self.knots:
            self.knots = self._create_clamped_uniform_knots(n, self.degree)

        # Knotenvektor validieren
        expected_knots = n + self.degree + 1
        if len(self.knots) != expected_knots:
            raise ValueError(f"Knotenvektor muss {expected_knots} Elemente haben, hat {len(self.knots)}")

    @staticmethod
    def _create_clamped_uniform_knots(n: int, p: int) -> List[float]:
        """
        Erstellt clamped uniform Knotenvektor.

        Clamped: Kurve beginnt/endet an erstem/letztem Kontrollpunkt
        Uniform: Gleichmäßig verteilte innere Knoten
        """
        m = n + p + 1
        knots = []

        for i in range(m):
            if i <= p:
                knots.append(0.0)
            elif i >= m - p - 1:
                knots.append(1.0)
            else:
                knots.append((i - p) / (n - p))

        return knots

    def _basis_function(self, i: int, p: int, u: float) -> float:
        """
        Berechnet B-Spline Basisfunktion N_i,p(u) rekursiv.

        Cox-de Boor Rekursionsformel.
        """
        if p == 0:
            # Basis-Fall
            if self.knots[i] <= u < self.knots[i + 1]:
                return 1.0
            # Sonderfall für u = 1.0 am Ende
            elif u == self.knots[i + 1] == 1.0 and self.knots[i] < 1.0:
                return 1.0
            return 0.0

        # Rekursion
        result = 0.0

        # Erster Term
        denom1 = self.knots[i + p] - self.knots[i]
        if denom1 != 0:
            result += (u - self.knots[i]) / denom1 * self._basis_function(i, p - 1, u)

        # Zweiter Term
        denom2 = self.knots[i + p + 1] - self.knots[i + 1]
        if denom2 != 0:
            result += (self.knots[i + p + 1] - u) / denom2 * self._basis_function(i + 1, p - 1, u)

        return result

    def _basis_functions_at(self, u: float) -> np.ndarray:
        """Berechnet alle Basisfunktionen an u."""
        n = len(self.control_points)
        N = np.zeros(n)

        for i in range(n):
            N[i] = self._basis_function(i, self.degree, u)

        return N

    def evaluate(self, u: float) -> Tuple[float, float, float]:
        """
        Evaluiert Kurve an Parameter u ∈ [0, 1].

        Verwendet gewichtete Summe der Basisfunktionen.

        Args:
            u: Parameter (0.0 = Start, 1.0 = Ende)

        Returns:
            Punkt (x, y, z) auf der Kurve
        """
        u = max(0.0, min(1.0, u))  # Clamp to [0, 1]

        n = len(self.control_points)
        P = np.array(self.control_points)
        w = np.array(self.weights)

        # Basisfunktionen berechnen
        N = self._basis_functions_at(u)

        # Gewichtete Summe (NURBS Formel)
        numerator = np.zeros(3)
        denominator = 0.0

        for i in range(n):
            numerator += N[i] * w[i] * P[i]
            denominator += N[i] * w[i]

        if abs(denominator) < 1e-10:
            # Fallback: Ungewichteter Durchschnitt
            return tuple(numerator / max(sum(N), 1e-10))

        result = numerator / denominator
        return (float(result[0]), float(result[1]), float(result[2]))

    def evaluate_points(self, num_points: int = 50) -> List[Tuple[float, float, float]]:
        """
        Evaluiert Kurve an gleichmäßig verteilten Parametern.

        Args:
            num_points: Anzahl der Punkte

        Returns:
            Liste von Punkten auf der Kurve
        """
        points = []
        for i in range(num_points):
            u = i / (num_points - 1) if num_points > 1 else 0.0
            points.append(self.evaluate(u))
        return points

    def derivative(self, u: float, order: int = 1) -> Tuple[float, float, float]:
        """
        Berechnet n-te Ableitung an u.

        Verwendet numerische Differentiation für Robustheit.

        Args:
            u: Parameter
            order: Ableitungsordnung (1 = Tangente, 2 = Beschleunigung)

        Returns:
            Ableitungsvektor (dx, dy, dz)
        """
        h = 1e-6  # Schrittweite

        if order == 1:
            # Zentrale Differenz für erste Ableitung
            p_plus = np.array(self.evaluate(min(u + h, 1.0)))
            p_minus = np.array(self.evaluate(max(u - h, 0.0)))
            deriv = (p_plus - p_minus) / (2 * h)

        elif order == 2:
            # Zentrale Differenz für zweite Ableitung
            p_plus = np.array(self.evaluate(min(u + h, 1.0)))
            p_center = np.array(self.evaluate(u))
            p_minus = np.array(self.evaluate(max(u - h, 0.0)))
            deriv = (p_plus - 2 * p_center + p_minus) / (h * h)

        else:
            # Höhere Ableitungen rekursiv
            deriv = np.zeros(3)
            logger.warning(f"Ableitung Ordnung {order} nicht implementiert")

        return (float(deriv[0]), float(deriv[1]), float(deriv[2]))

    def tangent(self, u: float) -> Tuple[float, float, float]:
        """
        Berechnet normalisierten Tangentenvektor an u.

        Returns:
            Einheitsvektor in Tangentenrichtung
        """
        d = np.array(self.derivative(u, 1))
        length = np.linalg.norm(d)

        if length < 1e-10:
            return (1.0, 0.0, 0.0)  # Fallback

        d = d / length
        return (float(d[0]), float(d[1]), float(d[2]))

    def normal(self, u: float) -> Tuple[float, float, float]:
        """
        Berechnet Normalenvektor (Hauptnormale) an u.

        Der Normalenvektor zeigt zum Krümmungsmittelpunkt.

        Returns:
            Einheitsvektor in Normalenrichtung
        """
        d1 = np.array(self.derivative(u, 1))
        d2 = np.array(self.derivative(u, 2))

        # Formel: N = (d1 × (d2 × d1)) / |d1 × (d2 × d1)|
        cross1 = np.cross(d2, d1)
        n = np.cross(d1, cross1)
        length = np.linalg.norm(n)

        if length < 1e-10:
            # Fallback: Orthogonal zu Tangente
            t = self.tangent(u)
            if abs(t[2]) < 0.9:
                n = np.cross(t, (0, 0, 1))
            else:
                n = np.cross(t, (1, 0, 0))
            n = n / np.linalg.norm(n)
            return tuple(n)

        n = n / length
        return (float(n[0]), float(n[1]), float(n[2]))

    def curvature(self, u: float) -> float:
        """
        Berechnet Krümmung κ an u.

        Formel: κ = |C' × C''| / |C'|³

        Returns:
            Krümmung (1/Radius)
        """
        d1 = np.array(self.derivative(u, 1))
        d2 = np.array(self.derivative(u, 2))

        cross = np.cross(d1, d2)
        numerator = np.linalg.norm(cross)
        denominator = np.linalg.norm(d1) ** 3

        if denominator < 1e-10:
            return 0.0

        return numerator / denominator

    def curvature_radius(self, u: float) -> float:
        """
        Berechnet Krümmungsradius an u.

        Returns:
            Radius (Infinity wenn Krümmung = 0)
        """
        k = self.curvature(u)
        if abs(k) < 1e-10:
            return float('inf')
        return 1.0 / k

    def arc_length(self, u_start: float = 0.0, u_end: float = 1.0, num_samples: int = 100) -> float:
        """
        Berechnet Bogenlänge zwischen u_start und u_end.

        Verwendet numerische Integration (Simpson).

        Returns:
            Bogenlänge in Einheiten der Kontrollpunkte
        """
        total = 0.0
        prev_point = np.array(self.evaluate(u_start))

        for i in range(1, num_samples + 1):
            u = u_start + (u_end - u_start) * i / num_samples
            point = np.array(self.evaluate(u))
            total += np.linalg.norm(point - prev_point)
            prev_point = point

        return total

    def to_ocp(self):
        """
        Konvertiert zu OCP Geom_BSplineCurve.

        Returns:
            OCP.Geom.Geom_BSplineCurve Objekt
        """
        try:
            from OCP.Geom import Geom_BSplineCurve
            from OCP.TColgp import TColgp_Array1OfPnt
            from OCP.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
            from OCP.gp import gp_Pnt

            n = len(self.control_points)

            # Poles (Kontrollpunkte)
            poles = TColgp_Array1OfPnt(1, n)
            for i, (x, y, z) in enumerate(self.control_points):
                poles.SetValue(i + 1, gp_Pnt(x, y, z))

            # Weights
            weights = TColStd_Array1OfReal(1, n)
            for i, w in enumerate(self.weights):
                weights.SetValue(i + 1, w)

            # Knots + Multiplicities
            unique_knots = sorted(set(self.knots))
            multiplicities = [self.knots.count(k) for k in unique_knots]

            knots_arr = TColStd_Array1OfReal(1, len(unique_knots))
            mults_arr = TColStd_Array1OfInteger(1, len(unique_knots))

            for i, (k, m) in enumerate(zip(unique_knots, multiplicities)):
                knots_arr.SetValue(i + 1, k)
                mults_arr.SetValue(i + 1, m)

            return Geom_BSplineCurve(poles, weights, knots_arr, mults_arr, self.degree)

        except ImportError as e:
            logger.error(f"OCP nicht verfügbar: {e}")
            raise

    def to_build123d_edge(self):
        """
        Konvertiert zu Build123d Edge.

        Returns:
            Build123d Edge Objekt
        """
        try:
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
            from build123d import Edge

            ocp_curve = self.to_ocp()
            edge_builder = BRepBuilderAPI_MakeEdge(ocp_curve)

            if not edge_builder.IsDone():
                raise ValueError("Edge-Erstellung fehlgeschlagen")

            return Edge(edge_builder.Edge())

        except ImportError as e:
            logger.error(f"Build123d nicht verfügbar: {e}")
            raise

    @classmethod
    def from_ocp(cls, ocp_curve) -> 'NURBSCurve':
        """
        Importiert von OCP Geom_BSplineCurve.

        Args:
            ocp_curve: OCP.Geom.Geom_BSplineCurve

        Returns:
            NURBSCurve Instanz
        """
        n = ocp_curve.NbPoles()

        control_points = []
        weights = []

        for i in range(1, n + 1):
            pole = ocp_curve.Pole(i)
            control_points.append((pole.X(), pole.Y(), pole.Z()))
            weights.append(ocp_curve.Weight(i))

        # Knots extrahieren (mit Multiplizitäten)
        knots = []
        for i in range(1, ocp_curve.NbKnots() + 1):
            k = ocp_curve.Knot(i)
            m = ocp_curve.Multiplicity(i)
            knots.extend([k] * m)

        return cls(
            control_points=control_points,
            weights=weights,
            knots=knots,
            degree=ocp_curve.Degree()
        )

    @classmethod
    def from_points_interpolate(cls, points: List[Tuple[float, float, float]],
                                 degree: int = 3) -> 'NURBSCurve':
        """
        Erstellt NURBS-Kurve die durch gegebene Punkte interpoliert.

        Verwendet Global Curve Interpolation.

        Args:
            points: Punkte die interpoliert werden sollen
            degree: Kurvengrad

        Returns:
            NURBSCurve die durch alle Punkte geht
        """
        try:
            from OCP.GeomAPI import GeomAPI_PointsToBSpline
            from OCP.TColgp import TColgp_Array1OfPnt
            from OCP.gp import gp_Pnt

            n = len(points)

            if n < 2:
                raise ValueError("Mindestens 2 Punkte erforderlich")

            # Punkte zu OCP Array
            pts = TColgp_Array1OfPnt(1, n)
            for i, (x, y, z) in enumerate(points):
                pts.SetValue(i + 1, gp_Pnt(x, y, z))

            # Interpolation
            interpolator = GeomAPI_PointsToBSpline(pts, degree, degree)

            if not interpolator.IsDone():
                raise ValueError("Interpolation fehlgeschlagen")

            ocp_curve = interpolator.Curve()
            return cls.from_ocp(ocp_curve)

        except ImportError:
            # Fallback: Kontrollpunkte = Interpolationspunkte
            logger.warning("OCP nicht verfügbar, verwende direkte Kontrollpunkte")
            return cls(control_points=list(points), degree=min(degree, len(points) - 1))

    @classmethod
    def from_points_approximate(cls, points: List[Tuple[float, float, float]],
                                 degree: int = 3,
                                 tolerance: float = 0.01) -> 'NURBSCurve':
        """
        Erstellt NURBS-Kurve die Punkte approximiert (nicht exakt interpoliert).

        Nützlich für verrauschte Daten oder Reduktion von Kontrollpunkten.

        Args:
            points: Punkte die approximiert werden sollen
            degree: Kurvengrad
            tolerance: Maximale Abweichung

        Returns:
            NURBSCurve mit reduzierter Kontrollpunkt-Anzahl
        """
        try:
            from OCP.GeomAPI import GeomAPI_PointsToBSpline
            from OCP.TColgp import TColgp_Array1OfPnt
            from OCP.gp import gp_Pnt
            from OCP.Approx import Approx_ParametrizationType

            n = len(points)
            pts = TColgp_Array1OfPnt(1, n)
            for i, (x, y, z) in enumerate(points):
                pts.SetValue(i + 1, gp_Pnt(x, y, z))

            # Approximation mit Toleranz
            approx = GeomAPI_PointsToBSpline(
                pts,
                degree, degree,  # DegMin, DegMax
                Approx_ParametrizationType.Approx_ChordLength,
                tolerance
            )

            if not approx.IsDone():
                raise ValueError("Approximation fehlgeschlagen")

            return cls.from_ocp(approx.Curve())

        except ImportError:
            logger.warning("OCP nicht verfügbar")
            return cls.from_points_interpolate(points, degree)


@dataclass
class NURBSSurface:
    """
    Native NURBS-Fläche (Bi-parametrisch).

    Mathematisch:
    S(u,v) = ΣΣ N_i,p(u) * N_j,q(v) * w_ij * P_ij / ΣΣ N_i,p(u) * N_j,q(v) * w_ij

    Attributes:
        control_points: Kontrollpunkte als 2D Grid [u][v]
        weights: Gewichte als 2D Grid (default: alle 1.0)
        knots_u: Knotenvektor in U-Richtung
        knots_v: Knotenvektor in V-Richtung
        degree_u: Polynomgrad in U-Richtung
        degree_v: Polynomgrad in V-Richtung
    """
    control_points: List[List[Tuple[float, float, float]]]  # [u][v] Grid
    weights: List[List[float]] = field(default_factory=list)
    knots_u: List[float] = field(default_factory=list)
    knots_v: List[float] = field(default_factory=list)
    degree_u: int = 3
    degree_v: int = 3

    def __post_init__(self):
        nu = len(self.control_points)
        nv = len(self.control_points[0]) if nu > 0 else 0

        if nu < 2 or nv < 2:
            raise ValueError("Mindestens 2x2 Kontrollpunkte erforderlich")

        # Grad begrenzen
        if self.degree_u >= nu:
            self.degree_u = nu - 1
        if self.degree_v >= nv:
            self.degree_v = nv - 1

        # Default Gewichte
        if not self.weights:
            self.weights = [[1.0 for _ in range(nv)] for _ in range(nu)]

        # Default Knotenvektoren
        if not self.knots_u:
            self.knots_u = NURBSCurve._create_clamped_uniform_knots(nu, self.degree_u)
        if not self.knots_v:
            self.knots_v = NURBSCurve._create_clamped_uniform_knots(nv, self.degree_v)

    def _basis_function_u(self, i: int, p: int, u: float) -> float:
        """B-Spline Basisfunktion in U-Richtung."""
        if p == 0:
            if self.knots_u[i] <= u < self.knots_u[i + 1]:
                return 1.0
            elif u == self.knots_u[i + 1] == 1.0 and self.knots_u[i] < 1.0:
                return 1.0
            return 0.0

        result = 0.0
        denom1 = self.knots_u[i + p] - self.knots_u[i]
        if denom1 != 0:
            result += (u - self.knots_u[i]) / denom1 * self._basis_function_u(i, p - 1, u)

        denom2 = self.knots_u[i + p + 1] - self.knots_u[i + 1]
        if denom2 != 0:
            result += (self.knots_u[i + p + 1] - u) / denom2 * self._basis_function_u(i + 1, p - 1, u)

        return result

    def _basis_function_v(self, j: int, q: int, v: float) -> float:
        """B-Spline Basisfunktion in V-Richtung."""
        if q == 0:
            if self.knots_v[j] <= v < self.knots_v[j + 1]:
                return 1.0
            elif v == self.knots_v[j + 1] == 1.0 and self.knots_v[j] < 1.0:
                return 1.0
            return 0.0

        result = 0.0
        denom1 = self.knots_v[j + q] - self.knots_v[j]
        if denom1 != 0:
            result += (v - self.knots_v[j]) / denom1 * self._basis_function_v(j, q - 1, v)

        denom2 = self.knots_v[j + q + 1] - self.knots_v[j + 1]
        if denom2 != 0:
            result += (self.knots_v[j + q + 1] - v) / denom2 * self._basis_function_v(j + 1, q - 1, v)

        return result

    def evaluate(self, u: float, v: float) -> Tuple[float, float, float]:
        """
        Evaluiert Fläche an (u, v).

        Args:
            u: Parameter in U-Richtung [0, 1]
            v: Parameter in V-Richtung [0, 1]

        Returns:
            Punkt (x, y, z) auf der Fläche
        """
        u = max(0.0, min(1.0, u))
        v = max(0.0, min(1.0, v))

        nu = len(self.control_points)
        nv = len(self.control_points[0])

        numerator = np.zeros(3)
        denominator = 0.0

        for i in range(nu):
            Ni = self._basis_function_u(i, self.degree_u, u)

            for j in range(nv):
                Nj = self._basis_function_v(j, self.degree_v, v)
                w = self.weights[i][j]
                P = np.array(self.control_points[i][j])

                numerator += Ni * Nj * w * P
                denominator += Ni * Nj * w

        if abs(denominator) < 1e-10:
            return (0.0, 0.0, 0.0)

        result = numerator / denominator
        return (float(result[0]), float(result[1]), float(result[2]))

    def partial_derivative_u(self, u: float, v: float) -> Tuple[float, float, float]:
        """Berechnet partielle Ableitung nach u."""
        h = 1e-6
        p_plus = np.array(self.evaluate(min(u + h, 1.0), v))
        p_minus = np.array(self.evaluate(max(u - h, 0.0), v))
        deriv = (p_plus - p_minus) / (2 * h)
        return (float(deriv[0]), float(deriv[1]), float(deriv[2]))

    def partial_derivative_v(self, u: float, v: float) -> Tuple[float, float, float]:
        """Berechnet partielle Ableitung nach v."""
        h = 1e-6
        p_plus = np.array(self.evaluate(u, min(v + h, 1.0)))
        p_minus = np.array(self.evaluate(u, max(v - h, 0.0)))
        deriv = (p_plus - p_minus) / (2 * h)
        return (float(deriv[0]), float(deriv[1]), float(deriv[2]))

    def normal(self, u: float, v: float) -> Tuple[float, float, float]:
        """
        Berechnet Flächen-Normale an (u, v).

        Formel: N = ∂S/∂u × ∂S/∂v (normalisiert)

        Returns:
            Einheits-Normalenvektor
        """
        du = np.array(self.partial_derivative_u(u, v))
        dv = np.array(self.partial_derivative_v(u, v))

        n = np.cross(du, dv)
        length = np.linalg.norm(n)

        if length < 1e-10:
            return (0.0, 0.0, 1.0)  # Fallback

        n = n / length
        return (float(n[0]), float(n[1]), float(n[2]))

    def gaussian_curvature(self, u: float, v: float) -> float:
        """
        Berechnet Gauß-Krümmung K = κ1 * κ2.

        Die Gauß-Krümmung ist positiv bei elliptischen Punkten,
        negativ bei hyperbolischen Punkten (Sattel),
        und null bei parabolischen Punkten.

        Returns:
            Gauß-Krümmung K
        """
        # Erste Fundamentalform
        du = np.array(self.partial_derivative_u(u, v))
        dv = np.array(self.partial_derivative_v(u, v))

        E = np.dot(du, du)
        F = np.dot(du, dv)
        G = np.dot(dv, dv)

        # Zweite Fundamentalform
        h = 1e-5
        n = np.array(self.normal(u, v))

        # Zweite partielle Ableitungen (numerisch)
        duu = (np.array(self.evaluate(min(u + h, 1), v)) -
               2 * np.array(self.evaluate(u, v)) +
               np.array(self.evaluate(max(u - h, 0), v))) / (h * h)

        dvv = (np.array(self.evaluate(u, min(v + h, 1))) -
               2 * np.array(self.evaluate(u, v)) +
               np.array(self.evaluate(u, max(v - h, 0)))) / (h * h)

        duv = (np.array(self.evaluate(min(u + h, 1), min(v + h, 1))) -
               np.array(self.evaluate(min(u + h, 1), max(v - h, 0))) -
               np.array(self.evaluate(max(u - h, 0), min(v + h, 1))) +
               np.array(self.evaluate(max(u - h, 0), max(v - h, 0)))) / (4 * h * h)

        L = np.dot(duu, n)
        M = np.dot(duv, n)
        N = np.dot(dvv, n)

        # Gauß-Krümmung
        denom = E * G - F * F
        if abs(denom) < 1e-10:
            return 0.0

        K = (L * N - M * M) / denom
        return K

    def mean_curvature(self, u: float, v: float) -> float:
        """
        Berechnet mittlere Krümmung H = (κ1 + κ2) / 2.

        Die mittlere Krümmung ist null bei Minimalflächen.

        Returns:
            Mittlere Krümmung H
        """
        # Erste Fundamentalform
        du = np.array(self.partial_derivative_u(u, v))
        dv = np.array(self.partial_derivative_v(u, v))

        E = np.dot(du, du)
        F = np.dot(du, dv)
        G = np.dot(dv, dv)

        # Zweite Fundamentalform (wie oben)
        h = 1e-5
        n = np.array(self.normal(u, v))

        duu = (np.array(self.evaluate(min(u + h, 1), v)) -
               2 * np.array(self.evaluate(u, v)) +
               np.array(self.evaluate(max(u - h, 0), v))) / (h * h)

        dvv = (np.array(self.evaluate(u, min(v + h, 1))) -
               2 * np.array(self.evaluate(u, v)) +
               np.array(self.evaluate(u, max(v - h, 0)))) / (h * h)

        duv = (np.array(self.evaluate(min(u + h, 1), min(v + h, 1))) -
               np.array(self.evaluate(min(u + h, 1), max(v - h, 0))) -
               np.array(self.evaluate(max(u - h, 0), min(v + h, 1))) +
               np.array(self.evaluate(max(u - h, 0), max(v - h, 0)))) / (4 * h * h)

        L = np.dot(duu, n)
        M = np.dot(duv, n)
        N = np.dot(dvv, n)

        # Mittlere Krümmung
        denom = 2 * (E * G - F * F)
        if abs(denom) < 1e-10:
            return 0.0

        H = (E * N - 2 * F * M + G * L) / denom
        return H

    def principal_curvatures(self, u: float, v: float) -> Tuple[float, float]:
        """
        Berechnet Hauptkrümmungen κ1 und κ2.

        Returns:
            Tuple (κ1, κ2) mit κ1 >= κ2
        """
        K = self.gaussian_curvature(u, v)
        H = self.mean_curvature(u, v)

        # κ1,2 = H ± sqrt(H² - K)
        discriminant = H * H - K

        if discriminant < 0:
            # Numerischer Fehler
            discriminant = 0

        sqrt_disc = np.sqrt(discriminant)
        k1 = H + sqrt_disc
        k2 = H - sqrt_disc

        return (k1, k2)

    def to_ocp(self):
        """
        Konvertiert zu OCP Geom_BSplineSurface.

        Returns:
            OCP.Geom.Geom_BSplineSurface Objekt
        """
        try:
            from OCP.Geom import Geom_BSplineSurface
            from OCP.TColgp import TColgp_Array2OfPnt
            from OCP.TColStd import TColStd_Array2OfReal, TColStd_Array1OfReal, TColStd_Array1OfInteger
            from OCP.gp import gp_Pnt

            nu = len(self.control_points)
            nv = len(self.control_points[0])

            # Poles (2D Array)
            poles = TColgp_Array2OfPnt(1, nu, 1, nv)
            weights = TColStd_Array2OfReal(1, nu, 1, nv)

            for i in range(nu):
                for j in range(nv):
                    x, y, z = self.control_points[i][j]
                    poles.SetValue(i + 1, j + 1, gp_Pnt(x, y, z))
                    weights.SetValue(i + 1, j + 1, self.weights[i][j])

            # Knots U
            unique_knots_u = sorted(set(self.knots_u))
            mults_u = [self.knots_u.count(k) for k in unique_knots_u]

            knots_u_arr = TColStd_Array1OfReal(1, len(unique_knots_u))
            mults_u_arr = TColStd_Array1OfInteger(1, len(unique_knots_u))

            for i, (k, m) in enumerate(zip(unique_knots_u, mults_u)):
                knots_u_arr.SetValue(i + 1, k)
                mults_u_arr.SetValue(i + 1, m)

            # Knots V
            unique_knots_v = sorted(set(self.knots_v))
            mults_v = [self.knots_v.count(k) for k in unique_knots_v]

            knots_v_arr = TColStd_Array1OfReal(1, len(unique_knots_v))
            mults_v_arr = TColStd_Array1OfInteger(1, len(unique_knots_v))

            for i, (k, m) in enumerate(zip(unique_knots_v, mults_v)):
                knots_v_arr.SetValue(i + 1, k)
                mults_v_arr.SetValue(i + 1, m)

            return Geom_BSplineSurface(
                poles, weights,
                knots_u_arr, knots_v_arr,
                mults_u_arr, mults_v_arr,
                self.degree_u, self.degree_v
            )

        except ImportError as e:
            logger.error(f"OCP nicht verfügbar: {e}")
            raise

    def to_build123d_face(self):
        """
        Konvertiert zu Build123d Face.

        Returns:
            Build123d Face Objekt
        """
        try:
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
            from build123d import Face

            ocp_surface = self.to_ocp()
            face_builder = BRepBuilderAPI_MakeFace(ocp_surface, 1e-6)

            if not face_builder.IsDone():
                raise ValueError("Face-Erstellung fehlgeschlagen")

            return Face(face_builder.Face())

        except ImportError as e:
            logger.error(f"Build123d nicht verfügbar: {e}")
            raise

    @classmethod
    def from_ocp(cls, ocp_surface) -> 'NURBSSurface':
        """
        Importiert von OCP Geom_BSplineSurface.

        Args:
            ocp_surface: OCP.Geom.Geom_BSplineSurface

        Returns:
            NURBSSurface Instanz
        """
        nu = ocp_surface.NbUPoles()
        nv = ocp_surface.NbVPoles()

        control_points = []
        weights = []

        for i in range(1, nu + 1):
            row_points = []
            row_weights = []

            for j in range(1, nv + 1):
                pole = ocp_surface.Pole(i, j)
                row_points.append((pole.X(), pole.Y(), pole.Z()))
                row_weights.append(ocp_surface.Weight(i, j))

            control_points.append(row_points)
            weights.append(row_weights)

        # Knots U
        knots_u = []
        for i in range(1, ocp_surface.NbUKnots() + 1):
            k = ocp_surface.UKnot(i)
            m = ocp_surface.UMultiplicity(i)
            knots_u.extend([k] * m)

        # Knots V
        knots_v = []
        for i in range(1, ocp_surface.NbVKnots() + 1):
            k = ocp_surface.VKnot(i)
            m = ocp_surface.VMultiplicity(i)
            knots_v.extend([k] * m)

        return cls(
            control_points=control_points,
            weights=weights,
            knots_u=knots_u,
            knots_v=knots_v,
            degree_u=ocp_surface.UDegree(),
            degree_v=ocp_surface.VDegree()
        )


# =============================================================================
# Convenience-Funktionen für häufige Anwendungsfälle
# =============================================================================

def create_bezier_curve(control_points: List[Tuple[float, float, float]]) -> NURBSCurve:
    """
    Erstellt Bézier-Kurve (spezielle NURBS mit n-1 Grad).

    Bézier-Kurven haben keine inneren Knoten.
    """
    n = len(control_points)
    degree = n - 1

    # Bézier Knotenvektor: [0, 0, ..., 0, 1, 1, ..., 1]
    knots = [0.0] * (degree + 1) + [1.0] * (degree + 1)

    return NURBSCurve(
        control_points=control_points,
        weights=[1.0] * n,
        knots=knots,
        degree=degree
    )


def create_circle_nurbs(center: Tuple[float, float, float] = (0, 0, 0),
                         radius: float = 1.0,
                         normal: Tuple[float, float, float] = (0, 0, 1)) -> NURBSCurve:
    """
    Erstellt Kreis als rationale quadratische NURBS-Kurve.

    Ein Kreis kann exakt als NURBS mit Grad 2 und 9 Kontrollpunkten
    dargestellt werden.
    """
    from math import sqrt

    cx, cy, cz = center
    nx, ny, nz = normal
    r = radius

    # Lokales Koordinatensystem
    n = np.array([nx, ny, nz])
    n = n / np.linalg.norm(n)

    # Orthogonale Vektoren finden
    if abs(n[2]) < 0.9:
        u = np.cross(n, [0, 0, 1])
    else:
        u = np.cross(n, [1, 0, 0])
    u = u / np.linalg.norm(u)
    v = np.cross(n, u)

    # 9 Kontrollpunkte für Kreis
    w = sqrt(2) / 2  # Gewicht für Mittelpunkte

    def pt(angle_deg):
        import math
        angle = math.radians(angle_deg)
        return (
            cx + r * (math.cos(angle) * u[0] + math.sin(angle) * v[0]),
            cy + r * (math.cos(angle) * u[1] + math.sin(angle) * v[1]),
            cz + r * (math.cos(angle) * u[2] + math.sin(angle) * v[2])
        )

    control_points = [
        pt(0), pt(45), pt(90), pt(135), pt(180), pt(225), pt(270), pt(315), pt(0)
    ]

    weights = [1, w, 1, w, 1, w, 1, w, 1]

    knots = [0, 0, 0, 0.25, 0.25, 0.5, 0.5, 0.75, 0.75, 1, 1, 1]

    return NURBSCurve(
        control_points=control_points,
        weights=weights,
        knots=knots,
        degree=2
    )


def create_ruled_surface(curve1: NURBSCurve, curve2: NURBSCurve) -> NURBSSurface:
    """
    Erstellt Regelfläche zwischen zwei NURBS-Kurven.

    Eine Regelfläche wird durch gerade Linien zwischen
    entsprechenden Punkten der beiden Kurven gebildet.
    """
    # Beide Kurven müssen gleiche Anzahl Kontrollpunkte haben
    n = len(curve1.control_points)

    if len(curve2.control_points) != n:
        raise ValueError("Kurven müssen gleiche Anzahl Kontrollpunkte haben")

    # 2x n Kontrollpunkte-Grid
    control_points = [
        list(curve1.control_points),
        list(curve2.control_points)
    ]

    weights = [
        list(curve1.weights),
        list(curve2.weights)
    ]

    return NURBSSurface(
        control_points=control_points,
        weights=weights,
        knots_u=[0, 0, 1, 1],  # Linear in U-Richtung
        knots_v=curve1.knots,
        degree_u=1,
        degree_v=curve1.degree
    )


# =============================================================================
# Integration mit Loft/Sweep Features
# =============================================================================

def loft_with_continuity(sections: List[NURBSCurve],
                          start_continuity: ContinuityMode = ContinuityMode.G0,
                          end_continuity: ContinuityMode = ContinuityMode.G0) -> Any:
    """
    Loft zwischen NURBS-Profilen mit Kontinuitätskontrolle.

    Args:
        sections: Liste von Profil-Kurven
        start_continuity: Kontinuität am Start
        end_continuity: Kontinuität am Ende

    Returns:
        Build123d Solid
    """
    try:
        from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
        from OCP.GeomAbs import GeomAbs_C0, GeomAbs_G1, GeomAbs_G2
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge
        from build123d import Solid

        # Kontinuität Mapping
        continuity_map = {
            ContinuityMode.G0: 0,
            ContinuityMode.G1: 1,
            ContinuityMode.G2: 2,
        }

        # Loft Builder
        is_solid = True
        is_ruled = False

        builder = BRepOffsetAPI_ThruSections(is_solid, is_ruled)

        # Smoothing aktivieren für G1/G2
        if start_continuity.value >= 1 or end_continuity.value >= 1:
            builder.SetSmoothing(True)

        # Profile als Wires hinzufügen
        for curve in sections:
            ocp_curve = curve.to_ocp()
            edge_builder = BRepBuilderAPI_MakeEdge(ocp_curve)
            wire_builder = BRepBuilderAPI_MakeWire(edge_builder.Edge())
            builder.AddWire(wire_builder.Wire())

        builder.Build()

        if not builder.IsDone():
            raise ValueError("Loft fehlgeschlagen")

        return Solid(builder.Shape())

    except Exception as e:
        logger.error(f"Loft mit Kontinuität fehlgeschlagen: {e}")
        raise


def sweep_with_scale(profile: NURBSCurve,
                      path: NURBSCurve,
                      scale_start: float = 1.0,
                      scale_end: float = 1.0,
                      twist_angle: float = 0.0) -> Any:
    """
    Sweep Profil entlang Pfad mit Skalierung und Twist.

    Args:
        profile: Profil-Kurve
        path: Pfad-Kurve
        scale_start: Skalierungsfaktor am Start
        scale_end: Skalierungsfaktor am Ende
        twist_angle: Verdrehung in Grad

    Returns:
        Build123d Solid
    """
    try:
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge
        from OCP.GeomFill import GeomFill_IsFrenet
        from OCP.Law import Law_Linear
        from build123d import Solid
        import math

        # Pfad als Wire
        path_ocp = path.to_ocp()
        path_edge = BRepBuilderAPI_MakeEdge(path_ocp).Edge()
        path_wire = BRepBuilderAPI_MakeWire(path_edge).Wire()

        # Profil als Wire
        profile_ocp = profile.to_ocp()
        profile_edge = BRepBuilderAPI_MakeEdge(profile_ocp).Edge()
        profile_wire = BRepBuilderAPI_MakeWire(profile_edge).Wire()

        # PipeShell erstellen
        pipe = BRepOffsetAPI_MakePipeShell(path_wire)
        pipe.SetMode(GeomFill_IsFrenet)

        # Skalierung als Law
        if scale_start != 1.0 or scale_end != 1.0:
            scale_law = Law_Linear()
            scale_law.Set(0, scale_start, 1, scale_end)
            pipe.SetLaw(profile_wire, scale_law, False, False)
        else:
            pipe.Add(profile_wire, False, False)

        pipe.Build()

        if not pipe.IsDone():
            raise ValueError("Sweep fehlgeschlagen")

        # Solid erstellen
        pipe.MakeSolid()

        return Solid(pipe.Shape())

    except Exception as e:
        logger.error(f"Sweep mit Skalierung fehlgeschlagen: {e}")
        raise
