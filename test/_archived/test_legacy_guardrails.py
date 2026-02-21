import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


RULES = [
    {
        "path": "modeling/__init__.py",
        "required": [
            r"\bdef\s+_resolve_path\(",
            r"\bdef\s+_compute_nsided_patch\(",
            r"if\s+isinstance\(feature,\s*\(ThreadFeature,\s*ExtrudeFeature\)\)",
            r"\"face_index\"\s*:\s*getattr\(feat,\s*\"face_index\"",
            r"has_topological_path_refs\s*=\s*bool\(",
            r"profile_face_index:\s*Optional\[int\]\s*=\s*None",
            r"profile_shape_id/profile_face_index",
            r"Kein Geometric-Fallback",
            r"\bdef\s+_collect_feature_reference_diagnostics\(",
            r"status_details:\s*dict\s*=\s*field\(default_factory=dict\)",
            r"Face-Referenz ist ungültig \(ShapeID/face_indices\)",
            r"Edge-Referenz ist ungültig \(ShapeID/edge_indices\)",
            r"Shell: Öffnungs-Faces konnten via TNP v4\.0 nicht aufgelöst werden",
        ],
        "forbidden": [
            r"\btnp_shape_reference\b",
            r"\bdef\s+_update_registry_for_feature\(",
            r"\bdef\s+_register_feature_shape_refs\(",
            r"\bdef\s+_unregister_feature_shape_refs\(",
            r"\bdef\s+_compute_extrude_legacy\(",
            r"\bdef\s+_load_legacy_format\(",
            r"\b_shape_registry\b",
            r"\btnp_data\b",
            r"BRepFeat Push/Pull ben.*face_selector",
            r"\"path_data\"\s*:\s*feat\.path_data",
            r"Sweep:\s*Legacy edge_selector migriert",
            r"N-Sided Patch:\s*Legacy-Selector nicht aufgelöst",
            r"edge_selectors:\s*list\s*=\s*field\(default_factory=list\)",
            r"NSidedPatchFeature\(\s*edge_selectors=",
        ],
    },
    {
        "path": "gui/main_window.py",
        "required": [
            r"\bdef\s+_preview_track_actor\(",
            r"\bdef\s+_preview_clear_group\(",
            r"\bdef\s+_clear_transient_previews\(",
            r"reason=f\"mode:\{prev_mode\}->\{mode\}\"",
            r"_clear_transient_previews\(reason=\"start_pattern\"",
            r"_clear_transient_previews\(reason=\"start_measure_mode\"",
            r"_clear_transient_previews\(reason=\"start_shell\"",
            r"_clear_transient_previews\(reason=\"start_texture_mode\"",
            r"_clear_transient_previews\(reason=\"start_sweep\"",
            r"_clear_transient_previews\(reason=\"start_loft\"",
            r"\bdef\s+_clear_measure_actors\(self,\s*render:\s*bool\s*=\s*True\)",
            r"\bdef\s+_clear_sweep_highlight\(self,\s*element_type:\s*str,\s*render:\s*bool\s*=\s*True\)",
            r"_preview_track_actor\(\"measure\",\s*actor_name\)",
            r"_preview_track_actor\(\"sweep_profile\",\s*actor_name\)",
            r"_preview_track_actor\(\"sweep_path\",\s*actor_name\)",
            r"\bface_from_index\(",
            r"\bdef\s+_resolve_solid_face_from_pick\(",
            r"face_shape_id=face_shape_id",
            r"face_index=best_face_index",
        ],
        "forbidden": [
            r"if\s+face_idx\s*==\s*ocp_face_id",
            r"edge_selectors\s*=\s*edge_selectors",
            r"\bget_edge_selectors\(",
            r"['\"]edge_selector['\"]\s*:\s*self\.viewport_3d\.get_edge_selectors\(",
            r"geometry_data\s*=\s*\(0,\s*0,\s*0,\s*0\)",
            r"TNP v3\.0:\s*Face-Selector f.r BRepFeat-Operationen",
            r"remove_actor\(\"sweep_profile_highlight\"",
            r"remove_actor\(\"sweep_path_highlight\"",
            r"remove_actor\(\"_measure_(pt_1|pt_2|line|label)\"",
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
        "path": "modeling/topology_indexing.py",
        "required": [
            r"\bdef\s+face_from_index\(",
            r"\bdef\s+edge_from_index\(",
            r"\bdef\s+iter_faces_with_indices\(",
            r"\bdef\s+iter_edges_with_indices\(",
        ],
    },
    {
        "path": "modeling/tnp_system.py",
        "required": [
            r"sweep_profile_shape_id\s*=\s*getattr\(feat,\s*\"profile_shape_id\"",
            r"sweep_profile_index\s*=\s*getattr\(feat,\s*\"profile_face_index\"",
            r"sweep_path_shape_id\s*=\s*getattr\(feat,\s*\"path_shape_id\"",
            r"path_data\.get\(\"edge_indices\"",
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
        "path": "gui/sketch_tools.py",
        "required": [
            r"VIRTUAL_INTERSECTION",
        ],
    },
    {
        "path": "gui/sketch_snapper.py",
        "required": [
            r"SnapType\.VIRTUAL_INTERSECTION",
            r"_priority_for_snap_type",
            r"_is_drawing_tool_active",
            r"_line_param",
            r"_no_snap_diagnostic",
            r"diagnostic=",
        ],
    },
    {
        "path": "gui/sketch_renderer.py",
        "required": [
            r"SnapType\.VIRTUAL_INTERSECTION",
        ],
    },
    {
        "path": "gui/viewport_pyvista.py",
        "required": [
            r"has_topological_refs\s*=\s*bool\(",
            r"face_shape_ids\s*=\s*list\(getattr\(feat,\s*\"face_shape_ids\"",
            r"if\s+not\s+added_from_topology\s+and\s+not\s+has_topological_refs",
        ],
    },
    {
        "path": "gui/widgets/tnp_stats_panel.py",
        "required": [
            r"\bdef\s+_status_detail_ref_lines\(",
            r"status_details",
            r"TNP-Detailanzeige fehlgeschlagen",
            r"feature_status",
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


def test_push_pull_has_single_topexp_import():
    """
    Regression-Guardrail: doppelte lokale Imports von TopExp_Explorer in
    _extrude_body_face_build123d verursachen UnboundLocalError durch Shadowing.
    """
    content = _read("gui/main_window.py")
    tree = ast.parse(content)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_extrude_body_face_build123d":
            target = node
            break

    assert target is not None, "gui/main_window.py: _extrude_body_face_build123d not found"

    import_count = 0
    for node in ast.walk(target):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "OCP.TopExp":
            continue
        for alias in node.names:
            if alias.name == "TopExp_Explorer":
                import_count += 1

    assert (
        import_count == 1
    ), "gui/main_window.py: _extrude_body_face_build123d must import TopExp_Explorer exactly once"
