"""
Script to remove duplicated methods from body.py that are now in mixin files.
Only removes methods that are already implemented in the mixins.
"""
import re
import shutil
import os

# Methods to remove (that are already fully implemented in mixins)
methods_to_remove = [
    # From BodyRebuildMixin
    '_rebuild',
    '_migrate_tnp_references',
    '_feature_has_topological_references',
    '_has_active_topological_references',
    # From BodyResolveMixin
    '_resolve_edges_tnp',
    '_validate_edge_in_solid',
    '_find_matching_edge_in_solid',
    '_is_same_edge',
    '_resolve_path',
    '_sketch_edge_to_wire',
    '_score_face_match',
    '_resolve_feature_faces',
    '_resolve_faces_for_shell',
    # From BodyExtrudeMixin
    '_extrude_from_face_brep',
    '_compute_extrude_part',
    '_compute_extrude_part_ocp_first',
    '_compute_extrude_part_legacy',
    '_compute_extrude_part_brepfeat',
    '_extrude_sketch_ellipses',
    '_extrude_single_ellipse',
    '_extrude_single_circle',
    '_extrude_single_slot',
    # From BodyComputeMixin (only these are implemented)
    '_compute_revolve',
    '_compute_loft',
]

def find_all_method_lines(filepath):
    """Find all method definitions and their line numbers."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    method_pattern = re.compile(r'^    def (\w+)\(')
    static_pattern = re.compile(r'^    @staticmethod')
    class_pattern = re.compile(r'^class ')
    
    all_methods = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check for @staticmethod before method
        if static_pattern.match(line):
            if i + 1 < len(lines):
                match = method_pattern.match(lines[i + 1])
                if match:
                    all_methods.append({
                        'name': match.group(1),
                        'start': i,  # Include @staticmethod (0-indexed)
                        'is_static': True
                    })
                    i += 2
                    continue
        match = method_pattern.match(line)
        if match:
            all_methods.append({
                'name': match.group(1),
                'start': i,  # 0-indexed
                'is_static': False
            })
        i += 1
    
    # Find end lines
    for idx, method in enumerate(all_methods):
        if idx + 1 < len(all_methods):
            method['end'] = all_methods[idx + 1]['start']
        else:
            # Find end of class (next top-level definition)
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
    
    # Filter to only methods we want to remove
    methods_to_remove_list = [m for m in all_methods if m['name'] in methods_to_remove]
    
    # Sort by start line in reverse order (remove from bottom up)
    methods_sorted = sorted(methods_to_remove_list, key=lambda m: m['start'], reverse=True)
    
    # Create backup
    backup_path = filepath + '.backup'
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
