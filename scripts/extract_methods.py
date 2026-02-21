#!/usr/bin/env python3
"""
Script to identify and delete duplicated methods from main_window.py
that already exist in mixin files.
"""
import re
import os

# Methods that exist in mixins and should be DELETED from main_window.py
METHODS_TO_DELETE = [
    # menu_actions.py
    "_new_project", "_save_project", "_save_project_as", "_do_save_project",
    "_open_project", "_load_project_from_path", "_update_recent_files_menu",
    "_open_recent_file", "_export_stl", "_export_stl_sync", "_export_stl_async",
    "_on_stl_export_finished", "_on_stl_export_error", "_export_step",
    "_on_step_export_finished", "_on_step_export_error", "_export_3mf",
    "_export_svg", "_import_step", "_import_svg", "_import_mesh_dialog",
    "_smart_undo", "_smart_redo", "_show_parameters_dialog",
    "_on_parameters_changed", "_resolve_feature_formulas", "_change_language",
    "_show_about", "_start_tutorial", "_get_export_candidates",
    
    # event_handlers.py
    "eventFilter", "_handle_key_press", "_handle_escape_key",
    "_should_block_shortcuts", "_handle_tab_key", "_handle_revolve_shortcuts",
    "_handle_draft_shortcuts", "_handle_3d_mode_shortcuts",
    "_handle_3d_global_shortcuts", "_handle_confirm_key",
    "_handle_plane_selection_shortcuts", "resizeEvent", "_on_opt_change",
    
    # sketch_operations.py
    "_new_sketch", "_on_plane_selected", "_on_custom_plane_selected",
    "_on_browser_plane_selected", "_create_sketch_at",
    "_set_sketch_body_references", "_start_offset_plane",
    "_start_offset_plane_drag", "_on_offset_plane_value_changed",
    "_on_offset_plane_drag", "_on_offset_plane_confirmed",
    "_on_offset_plane_cancelled", "_render_construction_planes",
    "_on_construction_plane_vis_changed", "_on_construction_plane_selected",
    "_finish_sketch", "_rotate_sketch_view", "_on_peek_3d",
    "_auto_align_sketch_view", "_on_sketch_changed_refresh_viewport",
    "_schedule_parametric_rebuild", "_do_parametric_rebuild",
    "_compute_profile_hash", "_update_bodies_depending_on_sketch",
    "_on_solver_dof_updated", "_on_sketch_tool_selected",
    
    # feature_operations.py
    "_extrude_dialog", "_on_viewport_height_changed",
    "_update_operation_from_height", "_on_extrude_panel_height_changed",
    "_on_extrude_operation_changed", "_on_to_face_requested",
    "_on_target_face_selected", "_on_face_selected_for_extrude",
    "_detect_extrude_operation", "_on_extrude_confirmed",
    "_on_extrude_cancelled", "_on_toggle_bodies_visibility",
    "_on_bodies_visibility_state_changed", "_update_detector",
    "_get_plane_from_sketch", "_on_extrusion_finished",
    "_find_body_closest_to_sketch", "_finish_extrusion_ui",
    "_delete_selected", "_edit_feature", "_edit_transform_feature",
    "_edit_parametric_feature", "_on_feature_deleted", "_on_feature_selected",
    "_on_rollback_changed", "_get_active_body", "_extrude_body_face_build123d",
    
    # viewport_operations.py
    "_trigger_viewport_update", "_update_viewport_all",
    "_update_viewport_all_impl", "_update_single_body",
    "_update_body_mesh", "_update_getting_started",
    "_focus_camera_on_bodies", "_reset_view", "_set_view_xy",
    "_set_view_xz", "_set_view_yz", "_set_view_isometric",
    "_zoom_to_fit", "_toggle_section_view", "_on_section_enabled",
    "_on_section_disabled", "_on_section_position_changed",
    "_on_section_plane_changed", "_on_section_invert_toggled",
    "_on_body_opacity_changed", "_hide_body", "_show_body",
    "_show_all_bodies", "_hide_all_bodies", "_position_extrude_panel",
    "_position_transform_panel", "_position_transform_toolbar",
    "_reposition_all_panels", "_set_mode", "_set_mode_fallback",
    "_on_body_transform_requested", "_apply_move", "_apply_rotate",
    "_apply_scale", "_calculate_plane_axes", "_find_component_for_body",
    "_is_body_in_inactive_component",
    
    # tool_operations.py
    "_on_3d_action", "_start_transform_mode", "_start_multi_body_transform",
    "_show_transform_ui", "_hide_transform_ui",
    "_on_transform_panel_confirmed", "_on_transform_panel_cancelled",
    "_on_transform_mode_changed", "_on_grid_size_changed",
    "_on_pivot_mode_changed", "_get_selected_body_id",
    "_on_transform_values_live_update", "_on_transform_val_change",
    "_on_viewport_transform_update", "_on_transform_confirmed",
    "_on_transform_cancelled", "_start_point_to_point_move",
    "_on_p2p_pick_body_requested", "_on_point_to_point_move",
    "_on_point_to_point_start_picked", "_on_point_to_point_cancelled",
    "_reset_point_to_point_move", "_cancel_point_to_point_move",
    "_start_measure_mode", "_on_measure_point_picked",
    "_clear_measure_actors", "_update_measure_visuals",
    "_update_measure_ui", "_on_measure_pick_requested",
    "_clear_measure_points", "_close_measure_panel",
    "_cancel_measure_mode", "_start_fillet", "_start_chamfer",
    "_start_fillet_chamfer_mode", "_on_body_clicked_for_fillet",
    "_activate_fillet_chamfer_for_body", "_on_edge_selection_changed",
    "_on_fillet_confirmed", "_on_fillet_radius_changed",
    "_on_fillet_cancelled", "_start_shell", "_start_sweep",
    "_start_loft", "_start_pattern", "_activate_pattern_for_body",
    "_start_texture_mode", "_activate_texture_for_body",
    "_show_not_implemented",
]

def find_method_ranges(content, method_names):
    """Find line ranges for each method that should be deleted."""
    lines = content.split('\n')
    method_ranges = []
    
    # Pattern for method definition (4 spaces indent for class method)
    method_pattern = re.compile(r'^    def (' + '|'.join(re.escape(m) for m in method_names) + r')\(')
    
    i = 0
    while i < len(lines):
        match = method_pattern.match(lines[i])
        if match:
            method_name = match.group(1)
            start_line = i + 1  # 1-indexed
            
            # Find end of method (next method or class def at same or lower indent)
            j = i + 1
            while j < len(lines):
                line = lines[j]
                # Check for next method/property/class at same indent level
                if line.startswith('    def ') or line.startswith('    @'):
                    break
                # Check for class-level definitions
                if re.match(r'^class ', line):
                    break
                # Check for section comments at same level
                if line.startswith('    # ='):
                    break
                j += 1
            
            end_line = j  # exclusive
            method_ranges.append((method_name, start_line, end_line))
            i = j
        else:
            i += 1
    
    return method_ranges

def main():
    main_window_path = os.path.join(os.path.dirname(__file__), '..', 'gui', 'main_window.py')
    
    with open(main_window_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_lines = len(content.split('\n'))
    print(f"Original line count: {original_lines}")
    
    # Find all method ranges to delete
    ranges = find_method_ranges(content, METHODS_TO_DELETE)
    
    print(f"\nFound {len(ranges)} methods to delete:")
    total_lines_to_remove = 0
    for name, start, end in ranges:
        lines = end - start + 1
        total_lines_to_remove += lines
        print(f"  {name}: lines {start}-{end} ({lines} lines)")
    
    print(f"\nTotal lines to remove: {total_lines_to_remove}")
    
    # Delete methods from bottom to top to preserve line numbers
    lines = content.split('\n')
    ranges_sorted = sorted(ranges, key=lambda x: x[1], reverse=True)
    
    for name, start, end in ranges_sorted:
        # Convert to 0-indexed
        del lines[start - 1:end]
        print(f"Deleted {name} (lines {start}-{end})")
    
    new_content = '\n'.join(lines)
    new_lines = len(lines)
    
    print(f"\nNew line count: {new_lines}")
    print(f"Lines removed: {original_lines - new_lines}")
    
    # Write back
    with open(main_window_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("\nFile updated successfully!")

if __name__ == '__main__':
    main()
