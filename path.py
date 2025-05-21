import json
import math
from itertools import permutations
from shapely.geometry import shape, Point, Polygon, LineString
import networkx as nx

# Load data (replace with actual data loading)
# Assume the user's data is structured into 'pois' and 'boundaries' GeoJSON features

# Example structure adjustment for the provided data:
# POIs are the initial Point features, boundaries are the Polygon features in the FeatureCollection

# Mock data parsing (replace with actual data)
with open("poi.geojson") as f:
    pois_data = json.load(f)["features"][:8]

with open("ieeta_for_path.json") as f:
    boundaries_data = json.load(f)["features"]

# Parse POIs
pois = []
for feature in pois_data:
    geom = shape(feature["geometry"])
    if isinstance(geom, Point):
        pois.append(geom)

# Parse boundaries
boundaries = []

for feaature in boundaries_data:
    geom = shape(feature["geometry"])
    if isinstance(geom, Polygon):
        boundaries.append(geom)

# Collect all nodes (POIs and polygon vertices)
nodes = []
# Add POIs
for poi in pois:
    nodes.append((poi.x, poi.y))
# Add polygon vertices from boundaries
for boundary in boundaries:
    ext_coords = list(boundary.exterior.coords)
    nodes.extend(ext_coords)
    for interior in boundary.interiors:
        nodes.extend(list(interior.coords))
# Deduplicate nodes
nodes = list(set(nodes))

# Build visibility graph
G = nx.Graph()

# Add nodes
for node in nodes:
    G.add_node(node)


# Function to check if a line is valid (doesn't intersect any boundary)
def is_valid_edge(p1, p2, boundaries):
    line = LineString([p1, p2])
    for boundary in boundaries:
        if line.intersects(boundary) and not line.touches(boundary):
            return False
    return True


# Add edges between nodes if valid
print("Building visibility graph...")
for i in range(len(nodes)):
    for j in range(i + 1, len(nodes)):
        p1 = nodes[i]
        p2 = nodes[j]
        if is_valid_edge(p1, p2, boundaries):
            distance = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            G.add_edge(p1, p2, weight=distance)

# Collect POI coordinates
poi_coords = [(poi.x, poi.y) for poi in pois]
n = len(poi_coords)

# Compute distance matrix between POIs
print("Computing distance matrix...")
distance_matrix = {}
for i in range(n):
    for j in range(n):
        if i == j:
            distance_matrix[(i, j)] = 0
            continue
        try:
            dist = nx.shortest_path_length(
                G, poi_coords[i], poi_coords[j], weight="weight"
            )
            distance_matrix[(i, j)] = dist
        except nx.NetworkXNoPath:
            distance_matrix[(i, j)] = float("inf")

# Solve TSP using brute-force permutations (feasible for n=9)
print("Solving TSP...")
best_order = None
min_distance = float("inf")
for perm in permutations(range(1, n)):
    current = [0] + list(perm)
    total = 0
    valid = True
    for a, b in zip(current, current[1:]):
        if distance_matrix[(a, b)] == float("inf"):
            valid = False
            break
        total += distance_matrix[(a, b)]
    if valid and total < min_distance:
        min_distance = total
        best_order = current

if not best_order:
    print("No valid path exists that visits all points.")
else:
    # Reconstruct the path
    full_path = []
    for i in range(len(best_order) - 1):
        a = best_order[i]
        b = best_order[i + 1]
        path = nx.shortest_path(G, poi_coords[a], poi_coords[b], weight="weight")
        full_path.extend(path)
    # Remove consecutive duplicates
    cleaned_path = []
    for p in full_path:
        if not cleaned_path or p != cleaned_path[-1]:
            cleaned_path.append(p)
    print("Optimal path coordinates:", cleaned_path)
