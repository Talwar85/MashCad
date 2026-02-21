"""
Script to remove more duplicated methods from body.py.
Phase 2: Extract remaining _compute_* and helper methods.
"""
import re
import shutil

# Additional methods to remove (to be added to body_compute_mixin.py)
methods_to_remove = [
    # Large _compute_* methods
    '_compute_sweep',
    '_move_profile_to_path_start',
    '_is_curved_path',
    '_compute_shell',
    '_compute_nsided_patch',
    '_compute_hollow',
    '_compute_hole',
    '_position_cylinder',
    '_compute_draft',
    '_compute_split',
    '_compute_thread',
    '_compute_thread_helix',
    '_compute_adaptive_edge_tolerance',
    # Helper methods for compute
    '_profile_data_to_face',
    '_unify_same_domain',
    # Canonicalization methods
    '_canonicalize_sweep_refs',
    '_canonicalize_loft_section_refs',
    '_canonicalize_edge_refs',
    '_canonicalize_face_refs',
    # Selector update methods
    '_update_edge_selectors_after_operation',
    '_update_edge_selectors_for_feature',
    '_update_face_selectors_for_feature',
    # TNP registration methods
    '_update_shape_naming_record',
    '_register_extrude_shapes',
    '_register_base_feature_shapes',
    '_register_brepfeat_operation',
    '_get_or_create_shape_naming_service',
    # OCP helpers
    '_ocp_extrude_face',
    '_ocp_fillet',
    '_ocp_chamfer',
    # Transform
    '_apply_transform_feature',
    # Profile helpers
    '_detect_circle_from_points',
    '_create_faces_from_native_circles',
    '_create_faces_from_native_arcs',
    '_detect_matching_native_spline',
    '_create_wire_from_native_spline',
    '_create_wire_from_mixed_geometry',
]

def find_all_method_lines(filepath):
    """Find all method definitions and their line numbers."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    method_pattern = re.compile(r'^    def (\w+)\(')
    static_pattern = re.compile(r'^    @staticmethod')
    
    all_methods = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if static_pattern.match(line):
            if i + 1 < len(lines):
                match = method_pattern.match(lines[i + 1])
                if match:
                    all_methods.append({
                        'name': match.group(1),
                        'start': i,
                        'is_static': True
                    })
                    i += 2
                    continue
        match = method_pattern.match(line)
        if match:
            all_methods.append({
                'name': match.group(1),
                'start': i,
                'is_static': False
            })
        i += 1
    
    for idx, method in enumerate(all_methods):
        if idx + 1 < len(all_methods):
            method['end'] = all_methods[idx + 1]['start']
        else:
            for i in range(method['start'] + 1, len(lines)):
                if re.match(r'^class |^def |^[A-Z]', lines[i]):
                    method['end'] = i
                    break
            else:
                method['end'] = len(lines)
    
    return all_methods, lines

def remove_methods(filepath):
    """Remove the specified methods from the file."""
    all_methods, lines = find_all_method_lines(filepath)
    
    methods_to_remove_list = [m for m in all_methods if m['name'] in methods_to_remove]
    methods_sorted = sorted(methods_to_remove_list, key=lambda m: m['start'], reverse=True)
    
    backup_path = filepath + '.backup2'
    shutil.copy(filepath, backup_path)
    print(f"Backup created: {backup_path}")
    
    total_removed = 0
    for method in methods_sorted:
        start = method['start']
        end = method['end']
        lines_removed = end - start
        total_removed += lines_removed
        print(f"Removing {method['name']}: lines {start+1}-{end} ({lines_removed} lines)")
        del lines[start:end]
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"\nTotal lines removed: {total_removed}")
    print(f"Final line count: {len(lines)}")
    return len(lines)

if __name__ == '__main__':
    final_count = remove_methods('modeling/body.py')
    if final_count > 2000:
        print(f"\nWARNING: File still has {final_count} lines (target: <2000)")
    else:
        print(f"\nSUCCESS: File reduced to {final_count} lines (target: <2000)")
