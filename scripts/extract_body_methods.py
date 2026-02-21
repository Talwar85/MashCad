"""
Script to identify and help remove duplicated methods from body.py
that are now in mixin files.
"""
import re

# Methods to remove (that are now in mixins)
methods_to_remove = [
    '_rebuild',
    '_migrate_tnp_references',
    '_feature_has_topological_references',
    '_has_active_topological_references',
    '_resolve_edges_tnp',
    '_validate_edge_in_solid',
    '_find_matching_edge_in_solid',
    '_is_same_edge',
    '_extrude_from_face_brep',
    '_compute_extrude_part',
    '_compute_extrude_part_ocp_first',
    '_compute_extrude_part_legacy',
    '_compute_extrude_part_brepfeat',
    '_extrude_sketch_ellipses',
    '_extrude_single_ellipse',
    '_extrude_single_circle',
    '_extrude_single_slot',
    '_resolve_path',
    '_sketch_edge_to_wire',
    '_score_face_match',
    '_resolve_feature_faces',
    '_resolve_faces_for_shell',
]

def find_method_ranges(filepath):
    """Find the start and end line numbers for each method."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find all method definitions
    method_pattern = re.compile(r'^    def (\w+)\(')
    static_method_pattern = re.compile(r'^    @staticmethod')
    
    methods_found = []
    
    for i, line in enumerate(lines):
        match = method_pattern.match(line)
        if match:
            method_name = match.group(1)
            if method_name in methods_to_remove:
                methods_found.append({
                    'name': method_name,
                    'start': i + 1,  # 1-indexed
                    'line': line.strip()[:60]
                })
    
    # Now find end lines (next method or class end)
    for idx, method in enumerate(methods_found):
        start = method['start']
        # Look for next method definition at same indentation
        if idx + 1 < len(methods_found):
            method['end'] = methods_found[idx + 1]['start'] - 1
        else:
            # Last method - find next method or end of class
            for i in range(start, len(lines)):
                if re.match(r'^    def \w+\(', lines[i]) and lines[i] not in [m['line'] for m in methods_found]:
                    method['end'] = i
                    break
                elif re.match(r'^class ', lines[i]):
                    method['end'] = i - 1
                    break
            else:
                method['end'] = len(lines)
    
    return methods_found

if __name__ == '__main__':
    methods = find_method_ranges('modeling/body.py')
    total_lines = 0
    for m in methods:
        lines = m.get('end', '?') - m['start'] + 1 if isinstance(m.get('end'), int) else '?'
        total_lines += lines if isinstance(lines, int) else 0
        print(f"{m['start']:5d}-{m.get('end', '?'):5d} ({lines:4d} lines): {m['name']}")
    print(f"\nTotal lines to remove: {total_lines}")
