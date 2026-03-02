"""
Explanation Schema for Print Optimization Results

This module defines the data structures for user-facing explanations
of print optimization recommendations.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class ExplanationType(Enum):
    """Type of explanation text."""
    IMPROVEMENT = "improvement"
    WARNING = "warning"
    INFO = "info"
    TRADEOFF = "tradeoff"


@dataclass
class MetricExplanation:
    """
    Explanation for a single metric comparison.

    Example:
        "Support volume reduced by 65% (8500 mm³ → 2975 mm³)"
    """
    metric_name: str
    before_value: float
    after_value: float
    unit: str
    improvement_percent: Optional[float] = None
    explanation_type: ExplanationType = ExplanationType.IMPROVEMENT

    def format(self) -> str:
        """Format as human-readable string."""
        if self.improvement_percent is not None:
            if self.improvement_percent > 0:
                return (
                    f"{self.metric_name}: {self.explanation_type.value} "
                    f"by {self.improvement_percent:.0f}% "
                    f"({self.before_value:.1f} → {self.after_value:.1f} {self.unit})"
                )
            elif self.improvement_percent < 0:
                return (
                    f"{self.metric_name}: increased by "
                    f"{-self.improvement_percent:.0f}% "
                    f"({self.before_value:.1f} → {self.after_value:.1f} {self.unit})"
                )
            else:
                return f"{self.metric_name}: unchanged"

        return f"{self.metric_name}: {self.before_value:.1f} {self.unit}"

    def to_dict(self) -> dict:
        """Serialize for UI/JSON."""
        return {
            'metric_name': self.metric_name,
            'before_value': self.before_value,
            'after_value': self.after_value,
            'unit': self.unit,
            'improvement_percent': self.improvement_percent,
            'explanation_type': self.explanation_type.value,
        }


@dataclass
class OrientationExplanation:
    """
    Full explanation for an orientation recommendation.

    Provides:
    - What changed (orientation description)
    - Why it's better (metrics breakdown)
    - What got better (improvements)
    - Any trade-offs (warnings)
    """
    orientation_description: str
    recommended_rotation: Optional[tuple]  # (axis_x, axis_y, axis_z), angle_degrees

    # Metrics that changed
    metrics: List[MetricExplanation]

    # Qualitative explanations
    improvements: List[str]
    warnings: List[str]
    tradeoffs: List[str]

    def to_dict(self) -> dict:
        """Serialize for UI/JSON."""
        return {
            'orientation_description': self.orientation_description,
            'recommended_rotation': self.recommended_rotation,
            'metrics': [m.to_dict() for m in self.metrics],
            'improvements': self.improvements,
            'warnings': self.warnings,
            'tradeoffs': self.tradeoffs,
        }

    def get_summary(self) -> str:
        """Get a one-paragraph summary for the user."""
        lines = [f"Recommended: {self.orientation_description}"]

        if self.improvements:
            lines.append("Improvements:")
            for imp in self.improvements:
                lines.append(f"  - {imp}")

        if self.warnings:
            lines.append("Warnings:")
            for warn in self.warnings:
                lines.append(f"  - {warn}")

        return "\n".join(lines)


# Template explanations for common scenarios

EXPLANATION_TEMPLATES = {
    'support_reduced': "Support volume reduced by {percent:.0f}% ({before:.0f} → {after:.0f} mm³)",
    'overhang_reduced': "Overhang area reduced by {percent:.0f}% ({before:.0f} → {after:.0f} mm²)",
    'stability_improved': "Base contact area increased ({before:.0f} → {after:.0f} mm²)",
    'height_increased': "Build height increased by {delta:.0f}mm (may affect print time)",
    'height_decreased': "Build height decreased by {delta:.0f}mm (faster print)",
    'bridge_preserved': "Bridge geometry preserved (no support needed)",
    'fin_proposed': "Support fins proposed for {count} unsupported region(s)",
}


def build_explanation(
    orientation_before: dict,
    orientation_after: dict,
    metrics_before: dict,
    metrics_after: dict,
    material: str = 'PLA'
) -> OrientationExplanation:
    """
    Build explanation from comparison of two orientations.

    Args:
        orientation_before: {'axis': (x,y,z), 'angle': deg}
        orientation_after: {'axis': (x,y,z), 'angle': deg}
        metrics_before: Dict of metric_name -> value
        metrics_after: Dict of metric_name -> value
        material: Material preset (affects bridge span limit)

    Returns:
        OrientationExplanation with all details
    """
    explanations = []
    warnings = []
    tradeoffs = []

    # Overhang comparison
    if metrics_before.get('overhang_area', 0) > metrics_after.get('overhang_area', 0):
        reduction = 100 * (
            1 - metrics_after['overhang_area'] / max(metrics_before['overhang_area'], 1)
        )
        explanations.append(MetricExplanation(
            metric_name="Overhang area",
            before_value=metrics_before['overhang_area'],
            after_value=metrics_after['overhang_area'],
            unit="mm²",
            improvement_percent=reduction
        ))

    # Support volume comparison
    if metrics_before.get('support_volume', 0) > metrics_after.get('support_volume', 0):
        reduction = 100 * (
            1 - metrics_after['support_volume'] / max(metrics_before['support_volume'], 1)
        )
        explanations.append(MetricExplanation(
            metric_name="Support volume",
            before_value=metrics_before['support_volume'],
            after_value=metrics_after['support_volume'],
            unit="mm³",
            improvement_percent=reduction
        ))

    # Build height comparison
    height_before = metrics_before.get('build_height', 0)
    height_after = metrics_after.get('build_height', 0)
    if abs(height_after - height_before) > 1.0:  # More than 1mm change
        explanations.append(MetricExplanation(
            metric_name="Build height",
            before_value=height_before,
            after_value=height_after,
            unit="mm",
            improvement_percent=height_before - height_after
        ))

    # Base contact comparison
    area_before = metrics_before.get('base_contact_area', 0)
    area_after = metrics_after.get('base_contact_area', 0)
    if area_after > area_before * 1.1:  # More than 10% improvement
        explanations.append(MetricExplanation(
            metric_name="Base contact area",
            before_value=area_before,
            after_value=area_after,
            unit="mm²",
            improvement_percent=100 * (area_after / max(area_before, 1) - 1)
        ))
    elif area_after < area_before * 0.9:  # Reduced by more than 10%
        warnings.append("Base contact area reduced (may affect stability)")

    # Trade-offs: taller build
    if height_after > height_before * 1.2:
        tradeoffs.append(
            f"Build height increased by {height_after - height_before:.0f}mm "
            f"(may add {((height_after - height_before) / 5):.0f} min print time)"
        )

    # Orientation description
    axis = orientation_after['axis']
    angle = orientation_after['angle']

    if axis == (0, 0, 1) and angle == 0:
        orientation_desc = "Upright (Z-axis up)"
    elif axis == (1, 0, 0) and angle == 90:
        orientation_desc = "On side (rotated around Y 90°)"
    elif axis == (0, 1, 0) and angle == 90:
        orientation_desc = "On side (rotated around X 90°)"
    else:
        orientation_desc = f"Rotated: axis={axis}, angle={angle}°"

    return OrientationExplanation(
        orientation_description=orientation_desc,
        recommended_rotation=(axis, angle),
        metrics=explanations,
        improvements=[e.format() for e in explanations],
        warnings=warnings,
        tradeoffs=tradeoffs
    )
