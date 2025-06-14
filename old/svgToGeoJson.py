import re
import json
import argparse
from xml.dom import minidom
from pathlib import Path


def parse_svg(svg_content):
    """Parse SVG content and extract path and rect elements with their points and styles"""
    doc = minidom.parseString(svg_content)
    elements = []

    # Handle paths
    paths = doc.getElementsByTagName('path')
    for path in paths:
        d = path.getAttribute('d')
        style = path.getAttribute('style')
        fill = path.getAttribute('fill')
        stroke = path.getAttribute('stroke')
        stroke_width = path.getAttribute('stroke-width')

        # Parse style attribute if present
        style_dict = {}
        if style:
            for prop in style.split(';'):
                if ':' in prop:
                    key, value = prop.split(':', 1)
                    style_dict[key.strip()] = value.strip()

        # Get attributes from style or direct attributes, with defaults
        final_fill = style_dict.get('fill', fill) or 'none'
        final_stroke = style_dict.get('stroke', stroke) or 'none'
        final_stroke_width = style_dict.get('stroke-width', stroke_width) or '1'

        points = []
        current_pos = [0, 0]
        subpaths = []  # To store separate subpaths

        # Split the path data into commands
        commands = re.findall(r'([MLHVCSQTAZmlhvcsqtaz])\s*([^MLHVCSQTAZmlhvcsqtaz]*)', d)

        for cmd in commands:
            command = cmd[0].upper()
            params = list(map(float, re.findall(r'[-+]?\d*\.?\d+', cmd[1])))

            if command == 'M':  # Move to (absolute)
                for i in range(0, len(params), 2):
                    current_pos = [params[i], params[i + 1]]
                    points.append(tuple(current_pos))
            elif command == 'L':  # Line to (absolute)
                for i in range(0, len(params), 2):
                    current_pos = [params[i], params[i + 1]]
                    points.append(tuple(current_pos))
            elif command == 'H':  # Horizontal line (absolute)
                for x in params:
                    current_pos[0] = x
                    points.append(tuple(current_pos))
            elif command == 'V':  # Vertical line (absolute)
                for y in params:
                    current_pos[1] = y
                    points.append(tuple(current_pos))
            elif command == 'Z':  # Close path
                if points and points[0] != points[-1]:
                    points.append(points[0])  # Close the polygon
                if points:
                    subpaths.append(points)
                    points = []

        # Add any remaining points that weren't closed with Z
        if points:
            subpaths.append(points)

        if subpaths:
            elements.append({
                'type': 'path',
                'subpaths': subpaths,
                'fill': final_fill,
                'stroke': final_stroke,
                'stroke_width': final_stroke_width
            })

    # Handle rectangles
    rects = doc.getElementsByTagName('rect')
    for rect in rects:
        x = float(rect.getAttribute('x'))
        y = float(rect.getAttribute('y'))
        width = float(rect.getAttribute('width'))
        height = float(rect.getAttribute('height'))
        style = rect.getAttribute('style')
        fill = rect.getAttribute('fill')
        stroke = rect.getAttribute('stroke')
        stroke_width = rect.getAttribute('stroke-width')

        # Parse style attribute if present
        style_dict = {}
        if style:
            for prop in style.split(';'):
                if ':' in prop:
                    key, value = prop.split(':', 1)
                    style_dict[key.strip()] = value.strip()

        # Get attributes from style or direct attributes, with defaults
        final_fill = style_dict.get('fill', fill) or 'none'
        final_stroke = style_dict.get('stroke', stroke) or 'none'
        final_stroke_width = style_dict.get('stroke-width', stroke_width) or '1'

        # Create rectangle as a polygon path
        points = [
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
            (x, y)  # Close the rectangle
        ]

        elements.append({
            'type': 'rect',
            'subpaths': [points],
            'fill': final_fill,
            'stroke': final_stroke,
            'stroke_width': final_stroke_width
        })

    doc.unlink()
    return elements


def calculate_bounds(elements):
    """Calculate min and max coordinates from all elements"""
    all_points = []
    for element in elements:
        for subpath in element.get('subpaths', []):
            all_points.extend(subpath)

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
        description='Georeference SVG using GeoJSON control points and extract polygons',
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
        geo_bounds = calculate_bounds([{'subpaths': [geo_points]}])

        # Create GeoJSON output with Polygon features
        features = []
        for i, element in enumerate(svg_elements):
            for j, subpath in enumerate(element.get('subpaths', [])):
                if len(subpath) < 3:  # Need at least 3 points for a polygon
                    continue

                geo_points = georeference_points(subpath, svg_bounds, geo_bounds)

                # Ensure the polygon is closed
                if geo_points[0] != geo_points[-1]:
                    geo_points.append(geo_points[0])

                properties = {
                    "id": f"{i}-{j}",
                    "element_type": element['type'],
                    "fill": element.get('fill', 'none'),
                    "stroke": element.get('stroke', 'none'),
                    "stroke_width": element.get('stroke_width', '1')
                }

                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [geo_points]
                    },
                    "properties": properties
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
        print(f"Successfully georeferenced {len(features)} polygons to {output_path}")

    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)


if __name__ == "__main__":
    main()