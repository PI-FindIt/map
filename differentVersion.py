import re
import json
import argparse
import numpy as np
from xml.dom import minidom
from pathlib import Path


def parse_svg(svg_content):
    """Parse SVG content and extract elements including control points with IDs."""
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

        style_dict = {}
        if style:
            for prop in style.split(';'):
                if ':' in prop:
                    key, value = prop.split(':', 1)
                    style_dict[key.strip()] = value.strip()

        final_fill = style_dict.get('fill', fill) or 'none'
        final_stroke = style_dict.get('stroke', stroke) or 'none'
        final_stroke_width = style_dict.get('stroke-width', stroke_width) or '1'

        points = []
        current_pos = [0, 0]
        subpaths = []

        commands = re.findall(r'([MLHVCSQTAZmlhvcsqtaz])\s*([^MLHVCSQTAZmlhvcsqtaz]*)', d)
        for cmd in commands:
            command = cmd[0].upper()
            params = list(map(float, re.findall(r'[-+]?\d*\.?\d+', cmd[1])))

            if command == 'M':
                for i in range(0, len(params), 2):
                    current_pos = [params[i], params[i + 1]]
                    points.append(tuple(current_pos))
            elif command == 'L':
                for i in range(0, len(params), 2):
                    current_pos = [params[i], params[i + 1]]
                    points.append(tuple(current_pos))
            elif command == 'H':
                for x in params:
                    current_pos[0] = x
                    points.append(tuple(current_pos))
            elif command == 'V':
                for y in params:
                    current_pos[1] = y
                    points.append(tuple(current_pos))
            elif command == 'Z':
                if points and points[0] != points[-1]:
                    points.append(points[0])
                if points:
                    subpaths.append(points)
                    points = []

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
        x = float(rect.getAttribute('x') or 0)
        y = float(rect.getAttribute('y') or 0)
        width = float(rect.getAttribute('width'))
        height = float(rect.getAttribute('height'))
        style = rect.getAttribute('style')
        fill = rect.getAttribute('fill')
        stroke = rect.getAttribute('stroke')
        stroke_width = rect.getAttribute('stroke-width')
        rect_id = rect.getAttribute('id') or None

        style_dict = {}
        if style:
            for prop in style.split(';'):
                if ':' in prop:
                    key, value = prop.split(':', 1)
                    style_dict[key.strip()] = value.strip()

        final_fill = style_dict.get('fill', fill) or 'none'
        final_stroke = style_dict.get('stroke', stroke) or 'none'
        final_stroke_width = style_dict.get('stroke-width', stroke_width) or '1'

        points = [
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
            (x, y)
        ]

        elements.append({
            'type': 'rect',
            'subpaths': [points],
            'fill': final_fill,
            'stroke': final_stroke,
            'stroke_width': final_stroke_width,
            'id': rect_id
        })

    doc.unlink()
    return elements


def main():
    parser = argparse.ArgumentParser(
        description='Georeference SVG using control points and extract polygons',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('svg_file', type=str, help='Path to SVG file')
    parser.add_argument('geojson_file', type=str, help='Path to GeoJSON file with control points')
    parser.add_argument('-o', '--output', type=str, default='output.geojson',
                        help='Output file path')

    args = parser.parse_args()

    try:
        # Read and parse SVG
        svg_path = Path(args.svg_file)
        if not svg_path.exists():
            raise FileNotFoundError(f"SVG file not found: {args.svg_file}")
        svg_content = svg_path.read_text()
        svg_elements = parse_svg(svg_content)

        # Extract SVG control points (A, B, C, D)
        svg_control_points = {}
        for element in svg_elements:
            if element.get('type') == 'rect' and element.get('id') in ['A', 'B', 'C', 'D']:
                rect_id = element['id']
                x, y = element['subpaths'][0][0]  # First point of the rect
                svg_control_points[rect_id] = (x, y)

        missing_svg = [id for id in ['A', 'B', 'C', 'D'] if id not in svg_control_points]
        if missing_svg:
            raise ValueError(f"Missing SVG control points: {missing_svg}")

        # Read and parse GeoJSON
        geojson_path = Path(args.geojson_file)
        if not geojson_path.exists():
            raise FileNotFoundError(f"GeoJSON file not found: {args.geojson_file}")
        geo_data = json.loads(geojson_path.read_text())

        geo_control_points = {}
        for feature in geo_data['features']:
            if feature['geometry']['type'] == 'Point' and 'id' in feature.get('properties', {}):
                point_id = feature['properties']['id']
                coords = feature['geometry']['coordinates']
                geo_control_points[point_id] = (coords[0], coords[1])

        missing_geo = [id for id in ['A', 'B', 'C', 'D'] if id not in geo_control_points]
        if missing_geo:
            raise ValueError(f"Missing GeoJSON control points: {missing_geo}")

        # Order points consistently
        ordered_ids = ['A', 'B', 'C', 'D']
        svg_coords = np.array([svg_control_points[id] for id in ordered_ids])
        geo_coords = np.array([geo_control_points[id] for id in ordered_ids])

        # Prepare matrices for affine transformation (least squares solution)
        x = svg_coords[:, 0]
        y = svg_coords[:, 1]
        A = np.column_stack([x, y, np.ones_like(x)])

        # Solve for longitude coefficients (a, b, c)
        B_lon = geo_coords[:, 0]
        coeff_lon, _, _, _ = np.linalg.lstsq(A, B_lon, rcond=None)

        # Solve for latitude coefficients (d, e, f)
        B_lat = geo_coords[:, 1]
        coeff_lat, _, _, _ = np.linalg.lstsq(A, B_lat, rcond=None)

        # Process all elements to create GeoJSON features
        features = []
        for i, element in enumerate(svg_elements):
            for j, subpath in enumerate(element.get('subpaths', [])):
                if len(subpath) < 3:
                    continue

                geo_points = []
                for (x_svg, y_svg) in subpath:
                    lon = coeff_lon[0] * x_svg + coeff_lon[1] * y_svg + coeff_lon[2]
                    lat = coeff_lat[0] * x_svg + coeff_lat[1] * y_svg + coeff_lat[2]
                    geo_points.append([lon, lat])

                # Close the polygon if not closed
                if geo_points and geo_points[0] != geo_points[-1]:
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

        # Write output
        output_path = Path(args.output)
        output_path.write_text(json.dumps(result, indent=2))
        print(f"Successfully georeferenced {len(features)} polygons to {output_path}")

    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)


if __name__ == "__main__":
    main()