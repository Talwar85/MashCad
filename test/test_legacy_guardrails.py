from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


RULES = [
    {
        "path": "modeling/__init__.py",
        "forbidden": [
            r"\btnp_shape_reference\b",
            r"\bdef\s+_update_registry_for_feature\(",
            r"\bdef\s+_register_feature_shape_refs\(",
            r"\bdef\s+_unregister_feature_shape_refs\(",
            r"\bdef\s+_compute_extrude_legacy\(",
            r"\bdef\s+_load_legacy_format\(",
            r"\b_shape_registry\b",
            r"\btnp_data\b",
            r"\"path_data\"\s*:\s*feat\.path_data",
        ],
    },
    {
        "path": "gui/main_window.py",
        "required": [
            r"\bface_from_index\(",
            r"\bdef\s+_resolve_solid_face_from_pick\(",
        ],
        "forbidden": [
            r"if\s+face_idx\s*==\s*ocp_face_id",
            r"edge_selectors\s*=\s*edge_selectors",
            r"['\"]edge_selector['\"]\s*:\s*self\.viewport_3d\.get_edge_selectors\(",
            r"geometry_data\s*=\s*\(0,\s*0,\s*0,\s*0\)",
        ],
    },
    {
        "path": "modeling/cad_tessellator.py",
        "required": [
            r"\biter_faces_with_indices\(",
        ],
        "forbidden": [
            r"face_id\s*\+=\s*1",
        ],
    },
    {
        "path": "modeling/textured_tessellator.py",
        "required": [
            r"\biter_faces_with_indices\(",
        ],
        "forbidden": [
            r"face_idx\s*\+=\s*1",
        ],
    },
    {
        "path": "gui/commands/feature_commands.py",
        "forbidden": [
            r"_register_feature_shape_refs\(",
            r"_unregister_feature_shape_refs\(",
        ],
    },
    {
        "path": "gui/sketch_handlers.py",
        "forbidden": [
            r"\bdef\s+_handle_trim_legacy\(",
            r"\bdef\s+_handle_trim_v2\(",
            r"_handle_trim_v2\(",
        ],
    },
    {
        "path": "sketcher/operations/trim.py",
        "forbidden": [
            r"\bclass\s+TrimComparisonTest\b",
            r"use_extracted_trim",
            r"\[TRIM V2\]",
        ],
    },
]

DUPLICATE_GUARDRAILS = [
    {
        "path": "gui/main_window.py",
        "pattern": r"\bdef\s+_update_viewport_all\(",
        "max_count": 1,
    },
]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_legacy_guardrails():
    failures = []

    for rule in RULES:
        rel_path = rule["path"]
        content = _read(rel_path)

        for pattern in rule.get("required", []):
            if re.search(pattern, content, flags=re.MULTILINE) is None:
                failures.append(f"{rel_path}: required pattern missing: {pattern}")

        for pattern in rule.get("forbidden", []):
            if re.search(pattern, content, flags=re.MULTILINE):
                failures.append(f"{rel_path}: forbidden pattern found: {pattern}")

    assert not failures, "\n".join(failures)


def test_duplicate_guardrails():
    failures = []

    for rule in DUPLICATE_GUARDRAILS:
        rel_path = rule["path"]
        content = _read(rel_path)
        count = len(re.findall(rule["pattern"], content, flags=re.MULTILINE))
        if count > rule["max_count"]:
            failures.append(
                f"{rel_path}: pattern appears {count}x (max {rule['max_count']}): {rule['pattern']}"
            )

    assert not failures, "\n".join(failures)
