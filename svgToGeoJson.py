import re
import json
import argparse
from xml.dom import minidom
from pathlib import Path


def parse_svg(svg_content):
    """Parse SVG content and extract all graphical elements with their points"""
    doc = minidom.parseString(svg_content)
    elements = []

    # Handle lines
    lines = doc.getElementsByTagName('line')
    for line in lines:
        x1 = float(line.getAttribute('x1')) if line.hasAttribute('x1') else 0
        y1 = float(line.getAttribute('y1')) if line.hasAttribute('y1') else 0
        x2 = float(line.getAttribute('x2')) if line.hasAttribute('x2') else 0
        y2 = float(line.getAttribute('y2')) if line.hasAttribute('y2') else 0
        elements.append({
            'type': 'line',
            'points': [(x1, y1), (x2, y2)]
        })

    # Handle paths
    paths = doc.getElementsByTagName('path')
    for path in paths:
        d = path.getAttribute('d')
        points = []
        path_points = re.findall(r'([MLVH])\s*([-\d.]+)\s*([-\d.]*)|([mlvh])\s*([-\d.]+)\s*([-\d.]*)', d)
        current_pos = [0, 0]

        for cmd in path_points:
            # Handle both uppercase (absolute) and lowercase (relative) commands
            if cmd[0]:  # Uppercase command
                c, x, y = cmd[0], cmd[1], cmd[2]
            else:  # Lowercase command
                c, x, y = cmd[3], cmd[4], cmd[5]

            if not x:
                continue

            x = float(x)
            y = float(y) if y else 0

            if c in ['M', 'L', 'm', 'l']:
                if c.islower():  # Relative
                    current_pos[0] += x
                    current_pos[1] += y
                else:  # Absolute
                    current_pos[0] = x
                    current_pos[1] = y
                points.append(tuple(current_pos))
            elif c in ['V', 'v']:  # Vertical line
                if c.islower():  # Relative
                    current_pos[1] += x
                else:  # Absolute
                    current_pos[1] = x
                points.append(tuple(current_pos))
            elif c in ['H', 'h']:  # Horizontal line
                if c.islower():  # Relative
                    current_pos[0] += x
                else:  # Absolute
                    current_pos[0] = x
                points.append(tuple(current_pos))

        if points:
            elements.append({
                'type': 'path',
                'points': points
            })

    doc.unlink()
    return elements


def calculate_bounds(elements):
    """Calculate min and max coordinates from all elements"""
    all_points = []
    for element in elements:
        all_points.extend(element['points'])

    if not all_points:
        return None

    x_coords = [p[0] for p in all_points]
    y_coords = [p[1] for p in all_points]
    return {
        'xmin': min(x_coords),
        'xmax': max(x_coords),
        'ymin': min(y_coords),
        'ymax': max(y_coords)
    }


def georeference_points(points, svg_bounds, geo_bounds):
    """Transform points from SVG to geographic coordinates with vertical flip"""
    # Calculate scale factors
    svg_width = svg_bounds['xmax'] - svg_bounds['xmin']
    svg_height = svg_bounds['ymax'] - svg_bounds['ymin']

    geo_width = geo_bounds['xmax'] - geo_bounds['xmin']
    geo_height = geo_bounds['ymax'] - geo_bounds['ymin']

    # Handle division by zero for flat SVGs
    if svg_width == 0:
        svg_width = 1
    if svg_height == 0:
        svg_height = 1

    # Transform each point with a vertical flip
    geo_referenced = []
    for x, y in points:
        # Normalize to bounds (note: 1-ny flips vertically)
        nx = (x - svg_bounds['xmin']) / svg_width
        ny = 1 - (y - svg_bounds['ymin']) / svg_height  # This flips the Y-axis

        # Apply to geographic bounds
        lon = geo_bounds['xmin'] + nx * geo_width
        lat = geo_bounds['ymin'] + ny * geo_height

        geo_referenced.append([lon, lat])

    return geo_referenced


def main():
    # Set up a command line argument parser
    parser = argparse.ArgumentParser(
        description='Georeference SVG using GeoJSON control points while preserving line connections',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('svg_file', type=str, help='Path to SVG file to georeference')
    parser.add_argument('geojson_file', type=str, help='Path to GeoJSON file with reference points')
    parser.add_argument('-o', '--output', type=str, default='output.geojson',
                        help='Output file path for georeferenced results')

    args = parser.parse_args()

    try:
        # Read SVG file
        svg_path = Path(args.svg_file)
        if not svg_path.exists():
            raise FileNotFoundError(f"SVG file not found: {args.svg_file}")
        svg_content = svg_path.read_text()

        # Read GeoJSON file
        geojson_path = Path(args.geojson_file)
        if not geojson_path.exists():
            raise FileNotFoundError(f"GeoJSON file not found: {args.geojson_file}")
        geojson_content = geojson_path.read_text()

        # Parse SVG and extract elements
        svg_elements = parse_svg(svg_content)
        if not svg_elements:
            raise ValueError("No graphical elements found in SVG file")
        svg_bounds = calculate_bounds(svg_elements)

        # Parse GeoJSON and extract points
        geo_data = json.loads(geojson_content)
        geo_points = []
        for feature in geo_data['features']:
            if feature['geometry']['type'] == 'Point':
                lon, lat = feature['geometry']['coordinates']
                geo_points.append((lon, lat))

        if not geo_points:
            raise ValueError("No Point features found in GeoJSON file")
        geo_bounds = calculate_bounds([{'points': geo_points}])

        # Create GeoJSON output with LineString features
        features = []
        for i, element in enumerate(svg_elements):
            geo_points = georeference_points(element['points'], svg_bounds, geo_bounds)

            if len(geo_points) < 2:
                # For single-point elements, create a Point feature instead
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": geo_points[0]
                    },
                    "properties": {
                        "id": i,
                        "element_type": element['type'],
                        "original_points": element['points']
                    }
                })
            else:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": geo_points
                    },
                    "properties": {
                        "id": i
                    }
                })

        result = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "made_by": "Violeta Batista Ramos",
                "pain_level": "max"
            }
        }

        # Write an output file
        output_path = Path(args.output)
        output_path.write_text(json.dumps(result, indent=2))
        print(f"Successfully georeferenced {len(features)} elements to {output_path}")

    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)


if __name__ == "__main__":
    main()