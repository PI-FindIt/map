import json
from shapely.geometry import Polygon, LineString, MultiLineString, Point
from pyproj import Proj, Transformer

# Configuration
N = 1  # meters can be changed easily

def load_polygon(geojson_path):
    with open(geojson_path, 'r') as f:
        data = json.load(f)
    coords = data['features'][0]['geometry']['coordinates'][0]
    return Polygon(coords)

def get_utm_zone(longitude):
    return int((longitude + 180) // 6) + 1

def project_to_utm(polygon):
    centroid = polygon.centroid
    lon, lat = centroid.x, centroid.y
    utm_zone = get_utm_zone(lon)
    hemisphere = 'north' if lat >= 0 else 'south'
    utm_proj = Proj(proj='utm', zone=utm_zone, ellps='WGS84', hemisphere=hemisphere)
    transformer = Transformer.from_proj(Proj('epsg:4326'), utm_proj, always_xy=True)
    utm_coords = [transformer.transform(x, y) for x, y in polygon.exterior.coords]
    return Polygon(utm_coords), transformer, utm_proj

def generate_grid_lines(polygon_utm, N):
    minx, miny, maxx, maxy = polygon_utm.bounds
    horizontal_lines = []
    vertical_lines = []

    # Horizontal lines
    y = miny
    while y <= maxy:
        line = LineString([(minx, y), (maxx, y)])
        intersection = line.intersection(polygon_utm)
        if not intersection.is_empty:
            if isinstance(intersection, LineString) and intersection.length >= N:
                horizontal_lines.append(intersection)
            elif isinstance(intersection, MultiLineString):
                for part in intersection.geoms:
                    if part.length >= N:
                        horizontal_lines.append(part)
        y += N - 1/3

    # Vertical lines
    x = minx
    while x <= maxx:
        line = LineString([(x, miny), (x, maxy)])
        intersection = line.intersection(polygon_utm)
        if not intersection.is_empty:
            if isinstance(intersection, LineString) and intersection.length >= N:
                vertical_lines.append(intersection)
            elif isinstance(intersection, MultiLineString):
                for part in intersection.geoms:
                    if part.length >= N:
                        vertical_lines.append(part)
        x += N - 1/3

    return horizontal_lines + vertical_lines

def main():
    polygon = load_polygon('path_tests/ideia_louca_da_vi.geojson')
    polygon_utm, transformer, utm_proj = project_to_utm(polygon)
    reverse_transformer = Transformer.from_proj(utm_proj, Proj('epsg:4326'), always_xy=True)
    edges = generate_grid_lines(polygon_utm, N)

    # Collect nodes
    nodes = {}
    node_id = 0
    for edge in edges:
        for coord in edge.coords:
            if coord not in nodes:
                nodes[coord] = node_id
                node_id += 1

    # Generate GeoJSON features
    features = []

    # Add nodes as Point features
    for coord_utm, nid in nodes.items():
        lon, lat = reverse_transformer.transform(coord_utm[0], coord_utm[1])
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {"id": nid, "stroke": "pink", "stroke_width": 1}
        })

    # Add edges as LineString features
    for edge_id, edge in enumerate(edges):
        coords_wgs84 = [reverse_transformer.transform(x, y) for x, y in edge.coords]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords_wgs84
            },
            "properties": {"edge_id": edge_id, "length_m": edge.length, "stroke": "pink", "stroke_width": 1}
        })

    # Write GeoJSON
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    with open('path_tests/closestPoint.geojson', 'w') as f:
        json.dump(geojson, f, indent=2)

if __name__ == "__main__":
    main()