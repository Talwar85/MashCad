"""
TNP v5.0 - Ambiguity Detection

Detects ambiguous resolution cases where user input is needed.
Provides user-friendly questions for disambiguation.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
from loguru import logger


class AmbiguityType(Enum):
    """Types of ambiguity that can occur during resolution."""

    SYMMETRIC = "symmetric"
    """Multiple candidates have symmetric positions (e.g., opposite faces of a cube)."""

    PROXIMATE = "proximate"
    """Multiple candidates are very close to the query point."""

    DUPLICATE = "duplicate"
    """Multiple candidates have identical matching scores."""

    INSUFFICIENT_CONTEXT = "insufficient_context"
    """Selection context is missing or incomplete."""

    MULTIPLE_FEATURES = "multiple_features"
    """Candidates belong to different features, requiring user intent."""


@dataclass
class AmbiguityReport:
    """
    Report describing an ambiguous resolution case.

    Attributes:
        ambiguity_type: The type of ambiguity detected
        question: User-friendly question describing the ambiguity
        candidates: List of candidate shape IDs
        candidate_descriptions: Human-readable descriptions for each candidate
        metadata: Additional information about the ambiguity
    """

    ambiguity_type: AmbiguityType
    question: str
    candidates: List[str]
    candidate_descriptions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate the ambiguity report."""
        if len(self.candidates) != len(self.candidate_descriptions):
            if not self.candidate_descriptions:
                # Generate default descriptions
                self.candidate_descriptions = [
                    f"Candidate {i + 1}" for i in range(len(self.candidates))
                ]


@dataclass
class CandidateInfo:
    """Information about a resolution candidate."""

    shape_id: str
    score: float
    distance: float
    shape_type: str
    feature_id: Optional[str] = None
    geometry_hash: Optional[str] = None
    center: Optional[Tuple[float, float, float]] = None


class AmbiguityDetector:
    """
    Detects ambiguous resolution cases requiring user input.

    Analyzes resolution candidates to identify:
    - Symmetric geometry (mirror positions)
    - Proximate candidates (very close together)
    - Duplicate scores (identical match quality)
    - Cross-feature ambiguities
    """

    def __init__(
        self,
        symmetry_threshold: float = 0.01,
        proximity_threshold: float = 0.1,
        score_difference_threshold: float = 0.05
    ):
        """
        Initialize the ambiguity detector.

        Args:
            symmetry_threshold: Distance threshold for detecting symmetric positions (mm)
            proximity_threshold: Distance threshold for detecting proximate candidates (mm)
            score_difference_threshold: Score difference threshold for duplicate detection
        """
        self._symmetry_threshold = symmetry_threshold
        self._proximity_threshold = proximity_threshold
        self._score_threshold = score_difference_threshold

    def detect(
        self,
        candidates: List[CandidateInfo],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[AmbiguityReport]:
        """
        Detect if resolution candidates are ambiguous.

        Args:
            candidates: List of candidate information
            context: Optional selection context

        Returns:
            AmbiguityReport if ambiguous, None if clear winner
        """
        if not candidates:
            return None

        if len(candidates) == 1:
            # Single candidate - no ambiguity
            return None

        # Sort by score (highest first)
        sorted_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)

        # Check for various ambiguity types (order matters for priority)
        # Symmetric positions are most specific
        report = self._check_symmetric_positions(sorted_candidates)
        if report:
            return report

        # Cross-feature ambiguity is also high priority
        report = self._check_multiple_features(sorted_candidates)
        if report:
            return report

        # Proximate positions
        report = self._check_proximate_positions(sorted_candidates)
        if report:
            return report

        # Duplicate scores
        report = self._check_duplicate_scores(sorted_candidates)
        if report:
            return report

        # Check if top candidates are very close in score
        report = self._check_close_scores(sorted_candidates)
        if report:
            return report

        # No ambiguity detected
        return None

    def _check_duplicate_scores(
        self,
        candidates: List[CandidateInfo]
    ) -> Optional[AmbiguityReport]:
        """
        Check if multiple candidates have identical scores.

        This indicates the matcher couldn't distinguish between them.
        """
        if len(candidates) < 2:
            return None

        top_score = candidates[0].score
        duplicates = [c for c in candidates if abs(c.score - top_score) < self._score_threshold]

        if len(duplicates) > 1:
            return self._create_duplicate_report(duplicates)

        return None

    def _check_symmetric_positions(
        self,
        candidates: List[CandidateInfo]
    ) -> Optional[AmbiguityReport]:
        """
        Check if candidates are in symmetric positions.

        For example, opposite faces of a rectangular solid.
        """
        if len(candidates) < 2:
            return None

        symmetric_groups = self._find_symmetric_groups(candidates)

        if symmetric_groups:
            # Return report for first symmetric group
            return self._create_symmetric_report(symmetric_groups[0])

        return None

    def _check_proximate_positions(
        self,
        candidates: List[CandidateInfo]
    ) -> Optional[AmbiguityReport]:
        """
        Check if multiple candidates are very close together.

        This makes it difficult to determine user intent.
        """
        if len(candidates) < 2:
            return None

        # Check if top candidates are within proximity threshold
        proximate = self._find_proximate_group(candidates[:3])

        if proximate and len(proximate) > 1:
            return self._create_proximate_report(proximate)

        return None

    def _check_multiple_features(
        self,
        candidates: List[CandidateInfo]
    ) -> Optional[AmbiguityReport]:
        """
        Check if top candidates belong to different features.

        This requires understanding user's feature-level intent.
        """
        if len(candidates) < 2:
            return None

        # Get unique features from top candidates
        top_candidates = candidates[:3]
        features = set()
        candidates_by_feature: Dict[str, List[CandidateInfo]] = {}

        for c in top_candidates:
            if c.feature_id:
                features.add(c.feature_id)
                if c.feature_id not in candidates_by_feature:
                    candidates_by_feature[c.feature_id] = []
                candidates_by_feature[c.feature_id].append(c)

        # If top candidates span multiple features with similar scores
        if len(features) > 1:
            # Check if top scores are close
            top_score = top_candidates[0].score
            close_candidates = [
                c for c in top_candidates
                if c.score >= top_score - self._score_threshold
            ]

            if len(close_candidates) > 1:
                return self._create_multiple_features_report(close_candidates)

        return None

    def _check_close_scores(
        self,
        candidates: List[CandidateInfo]
    ) -> Optional[AmbiguityReport]:
        """
        Check if top candidates have very close scores.

        Even if not strictly duplicate, close scores indicate uncertainty.
        """
        if len(candidates) < 2:
            return None

        top_score = candidates[0].score
        second_score = candidates[1].score

        if abs(top_score - second_score) < self._score_threshold:
            return self._create_close_scores_report(candidates[:2])

        return None

    def _find_symmetric_groups(
        self,
        candidates: List[CandidateInfo]
    ) -> List[List[CandidateInfo]]:
        """
        Find groups of candidates in symmetric positions.

        Returns list of candidate groups that are symmetric.
        """
        if len(candidates) < 2:
            return []

        groups = []
        processed = set()

        for i, c1 in enumerate(candidates):
            if i in processed or not c1.center:
                continue

            group = [c1]

            for j, c2 in enumerate(candidates[i + 1:], start=i + 1):
                if j in processed or not c2.center:
                    continue

                if self._are_symmetric(c1, c2):
                    group.append(c2)
                    processed.add(j)

            if len(group) > 1:
                groups.append(group)
                processed.add(i)

        return groups

    def _are_symmetric(self, c1: CandidateInfo, c2: CandidateInfo) -> bool:
        """
        Check if two candidates are symmetrically positioned.

        Simple check: positions are mirror images across an axis plane.
        """
        if not c1.center or not c2.center:
            return False

        x1, y1, z1 = c1.center
        x2, y2, z2 = c2.center

        # Check for mirror symmetry across XY, XZ, or YZ planes
        # Mirror across Z=0: (x, y, z) <-> (x, y, -z)
        if abs(x1 - x2) < self._symmetry_threshold and abs(y1 - y2) < self._symmetry_threshold:
            if abs(z1 + z2) < self._symmetry_threshold:
                return True

        # Mirror across Y=0: (x, y, z) <-> (x, -y, z)
        if abs(x1 - x2) < self._symmetry_threshold and abs(z1 - z2) < self._symmetry_threshold:
            if abs(y1 + y2) < self._symmetry_threshold:
                return True

        # Mirror across X=0: (x, y, z) <-> (-x, y, z)
        if abs(y1 - y2) < self._symmetry_threshold and abs(z1 - z2) < self._symmetry_threshold:
            if abs(x1 + x2) < self._symmetry_threshold:
                return True

        return False

    def _find_proximate_group(
        self,
        candidates: List[CandidateInfo]
    ) -> List[CandidateInfo]:
        """
        Find candidates that are within proximity threshold of each other.
        """
        if len(candidates) < 2:
            return []

        if not candidates[0].center:
            return []

        group = [candidates[0]]
        center_x, center_y, center_z = candidates[0].center

        for c in candidates[1:]:
            if not c.center:
                continue

            cx, cy, cz = c.center
            distance = ((cx - center_x)**2 + (cy - center_y)**2 + (cz - center_z)**2)**0.5

            if distance <= self._proximity_threshold:
                group.append(c)

        return group

    def _create_duplicate_report(self, candidates: List[CandidateInfo]) -> AmbiguityReport:
        """Create report for duplicate score ambiguity."""
        descriptions = []
        for c in candidates:
            desc = f"{c.shape_type}"
            if c.feature_id:
                desc += f" from {c.feature_id}"
            if c.center:
                desc += f" at ({c.center[0]:.1f}, {c.center[1]:.1f}, {c.center[2]:.1f})"
            descriptions.append(desc)

        question = self._format_question(
            "Multiple shapes have identical match scores. ",
            candidates
        )

        return AmbiguityReport(
            ambiguity_type=AmbiguityType.DUPLICATE,
            question=question,
            candidates=[c.shape_id for c in candidates],
            candidate_descriptions=descriptions,
            metadata={"score": candidates[0].score}
        )

    def _create_symmetric_report(self, candidates: List[CandidateInfo]) -> AmbiguityReport:
        """Create report for symmetric position ambiguity."""
        descriptions = []
        for c in candidates:
            if c.center:
                desc = f"{c.shape_type} at ({c.center[0]:.1f}, {c.center[1]:.1f}, {c.center[2]:.1f})"
            else:
                desc = f"{c.shape_type}"
            descriptions.append(desc)

        question = self._format_question(
            "Found shapes in symmetric positions. ",
            candidates
        )

        return AmbiguityReport(
            ambiguity_type=AmbiguityType.SYMMETRIC,
            question=question,
            candidates=[c.shape_id for c in candidates],
            candidate_descriptions=descriptions,
            metadata={"symmetric": True}
        )

    def _create_proximate_report(self, candidates: List[CandidateInfo]) -> AmbiguityReport:
        """Create report for proximate position ambiguity."""
        descriptions = []
        for c in candidates:
            if c.center and c.distance is not None:
                desc = f"{c.shape_type} (distance: {c.distance:.2f}mm)"
            else:
                desc = f"{c.shape_type}"
            descriptions.append(desc)

        question = self._format_question(
            "Found shapes very close to each other. ",
            candidates
        )

        return AmbiguityReport(
            ambiguity_type=AmbiguityType.PROXIMATE,
            question=question,
            candidates=[c.shape_id for c in candidates],
            candidate_descriptions=descriptions,
            metadata={"proximity_threshold": self._proximity_threshold}
        )

    def _create_multiple_features_report(self, candidates: List[CandidateInfo]) -> AmbiguityReport:
        """Create report for cross-feature ambiguity."""
        descriptions = []
        for c in candidates:
            desc = f"{c.shape_type}"
            if c.feature_id:
                desc += f" from '{c.feature_id}'"
            if c.score is not None:
                desc += f" (score: {c.score:.2f})"
            descriptions.append(desc)

        question = self._format_question(
            "Found shapes from different features. ",
            candidates
        )

        return AmbiguityReport(
            ambiguity_type=AmbiguityType.MULTIPLE_FEATURES,
            question=question,
            candidates=[c.shape_id for c in candidates],
            candidate_descriptions=descriptions,
            metadata={
                "features": list(set(c.feature_id for c in candidates if c.feature_id))
            }
        )

    def _create_close_scores_report(self, candidates: List[CandidateInfo]) -> AmbiguityReport:
        """Create report for close score ambiguity."""
        descriptions = []
        for i, c in enumerate(candidates):
            desc = f"{c.shape_type}"
            if c.feature_id:
                desc += f" from {c.feature_id}"
            if c.score is not None:
                desc += f" (score: {c.score:.2f})"
            descriptions.append(desc)

        scores_str = ", ".join(f"{c.score:.2f}" for c in candidates)
        question = (
            f"Found shapes with very similar match scores ({scores_str}). "
        )
        question += self._format_selection_instruction(candidates)

        return AmbiguityReport(
            ambiguity_type=AmbiguityType.DUPLICATE,
            question=question,
            candidates=[c.shape_id for c in candidates],
            candidate_descriptions=descriptions,
            metadata={"scores": [c.score for c in candidates]}
        )

    def _format_question(self, prefix: str, candidates: List[CandidateInfo]) -> str:
        """Format a user-friendly question."""
        question = prefix
        question += self._format_selection_instruction(candidates)
        return question

    def _format_selection_instruction(self, candidates: List[CandidateInfo]) -> str:
        """Format instruction for selecting from candidates."""
        if len(candidates) == 2:
            return "Which shape did you intend?"
        else:
            return f"Which of these {len(candidates)} shapes did you intend?"


def detect_ambiguity(
    candidates: List[Dict[str, Any]],
    threshold: float = 0.05
) -> Optional[AmbiguityReport]:
    """
    Convenience function to detect ambiguity in resolution results.

    Args:
        candidates: List of candidate dictionaries with 'shape_id', 'score', etc.
        threshold: Score difference threshold for ambiguity detection

    Returns:
        AmbiguityReport if ambiguous, None otherwise
    """
    if not candidates or len(candidates) < 2:
        return None

    detector = AmbiguityDetector(score_difference_threshold=threshold)

    # Convert dict candidates to CandidateInfo
    candidate_infos = []
    for c in candidates:
        info = CandidateInfo(
            shape_id=c.get('shape_id', ''),
            score=c.get('score', 0.0),
            distance=c.get('distance', 0.0),
            shape_type=c.get('shape_type', 'UNKNOWN'),
            feature_id=c.get('feature_id'),
            geometry_hash=c.get('geometry_hash'),
            center=c.get('center')
        )
        candidate_infos.append(info)

    return detector.detect(candidate_infos)
