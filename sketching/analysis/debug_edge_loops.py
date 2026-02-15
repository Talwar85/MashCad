import numpy as np
from collections import defaultdict

def extract_loops(lines, points):
    """
    Extract closed loops from line segments.
    lines: list of point index pairs [[p1, p2], [p2, p3], ...]
    points: values of points
    """
    # 1. Build Adjacency Graph
    adj = defaultdict(list)
    for i, (u, v) in enumerate(lines):
        adj[u].append((v, i))
        adj[v].append((u, i))
        
    visited_edges = set()
    loops = []
    
    # 2. Walk graph
    for start_node in list(adj.keys()):
        # Try to find a loop from this node
        # DFS/BFS?
        # Since we want simple loops (holes), we just follow the path.
        # At each node, if degree != 2, it's a junction or open end.
        pass
        
    # Better approach:
    # Iterate all edges. If not visited, start walking.
    for i, (u, v) in enumerate(lines):
        if i in visited_edges:
            continue
            
        # Start walking from u -> v
        current_loop = [u]
        current_node = v
        path_edges = {i}
        
        # We need to look for next edge from v
        # But we must not go back to u (unless loop closed)
        prev_node = u
        
        while True:
            current_loop.append(current_node)
            
            # Find neighbors of current_node
            neighbors = adj[current_node]
            
            # Find next unvisited edge (or visited if closing loop)
            next_step = None
            
            for next_node, edge_idx in neighbors:
                if edge_idx in path_edges:
                    continue # Already traversed in this path
                    
                # If degree > 2, we have a junction. 
                # For simple holes, degree should be exactly 2.
                # If degree > 2, it's a complex edge structure.
                # We can stop or pick one.
                
                next_step = (next_node, edge_idx)
                break
            
            if next_step:
                next_node, edge_idx = next_step
                path_edges.add(edge_idx)
                prev_node = current_node
                current_node = next_node
                
                if current_node == current_loop[0]:
                    # Closed Loop!
                    visited_edges.update(path_edges)
                    loops.append(current_loop)
                    break
            else:
                # Dead end
                visited_edges.update(path_edges)
                break
                
    return loops

def is_circle(loop_indices, points):
    pts = points[loop_indices]
    
    # 1. Fit Plane (SVD)
    centroid = np.mean(pts, axis=0)
    centered = pts - centroid
    U, S, Vt = np.linalg.svd(centered)
    normal = Vt[-1]
    
    # Check planarity (min variance should be small)
    thickness = S[-1]
    if thickness > 0.1 * S[-2]: # Not planar enough
        return False, None
    
    # 2. Check Radius consistency
    # Project to 2D
    # ...
    # Radius = mean distance from centroid
    dists = np.linalg.norm(centered, axis=1)
    mean_r = np.mean(dists)
    std_r = np.std(dists)
    
    if std_r / mean_r < 0.1: # 10% deviation allowed
        return True, (centroid, normal, mean_r)
        
    return False, None

# Test Data (Square + Circle)
points = np.array([
    [0,0,0], [10,0,0], [10,10,0], [0,10,0], # Square
    [20,0,0], [21,1,0], [20,2,0], [19,1,0]  # Diamond (Circle approx)
])

# Square Lines
lines = [
    [0,1], [1,2], [2,3], [3,0]
]
# Diamond Lines
lines += [
    [4,5], [5,6], [6,7], [7,4]
]

print("Extracting...")
loops = extract_loops(lines, points)
print(f"Found {len(loops)} loops")

for loop in loops:
    is_circ, params = is_circle(loop, points)
    print(f"Loop len={len(loop)}, IsCircle={is_circ}")
    if is_circ:
        c, n, r = params
        print(f"  R={r:.2f}, Center={c}")
