import re
import json
import argparse
import numpy as np
import cv2
from xml.dom import minidom
from pathlib import Path


def safe_float(value, default=0.0):
    """Safely convert string to float with fallback"""
    try:
        return float(value) if value.strip() else default
    except (ValueError, AttributeError, TypeError):
        return default


def parse_control_points(svg_content, geojson_data):
    """Extract and validate control points from both sources"""
    svg_doc = minidom.parseString(svg_content)
    svg_points = {}

    # Extract SVG control points
    for rect in svg_doc.getElementsByTagName('rect'):
        if rect.getAttribute('fill').lower() == 'pink':
            point_id = rect.getAttribute('id')
            if not point_id:
                continue

            x = safe_float(rect.getAttribute('x'))
            y = safe_float(rect.getAttribute('y'))

            if None in (x, y):
                raise ValueError(f"Control point {point_id} has invalid coordinates")

            svg_points[point_id] = (x, y)

    # Extract GeoJSON control points
    geo_points = {}
    for feature in geojson_data['features']:
        if feature['geometry']['type'] == 'Point':
            props = feature.get('properties', {})
            point_id = props.get('id')
            if point_id:
                coords = feature['geometry']['coordinates']
                if len(coords) >= 2:
                    geo_points[point_id] = (coords[0], coords[1])

    # Validation
    missing_svg = set(geo_points.keys()) - set(svg_points.keys())
    missing_geo = set(svg_points.keys()) - set(geo_points.keys())

    if missing_svg:
        raise ValueError(f"GeoJSON points missing in SVG: {missing_svg}")
    if missing_geo:
        raise ValueError(f"SVG points missing in GeoJSON: {missing_geo}")
    if len(svg_points) < 4:
        raise ValueError("At least 4 control points required")

    return svg_points, geo_points


def calculate_homography(svg_points, geo_points):
    """Compute homography matrix with RANSAC"""
    point_ids = sorted(svg_points.keys())

    src = np.array([svg_points[i] for i in point_ids], dtype=np.float32)
    dst = np.array([geo_points[i] for i in point_ids], dtype=np.float32)

    H, mask = cv2.findHomography(src.reshape(-1, 1, 2),
                                 dst.reshape(-1, 1, 2),
                                 cv2.RANSAC,
                                 ransacReprojThreshold=3.0)
    if H is None:
        raise ValueError("Homography calculation failed")

    return H


def transform_svg_elements(svg_elements, H):
    """Transform all SVG elements using homography"""
    features = []
    for idx, element in enumerate(svg_elements):
        element_type = element.get('type', 'unknown')
        subpaths = element.get('subpaths', [])

        for sub_idx, subpath in enumerate(subpaths):
            if len(subpath) < 2:
                continue

            # Convert to numpy array
            points_np = np.array(subpath, dtype=np.float32).reshape(-1, 1, 2)

            try:
                # Apply perspective transformation
                transformed = cv2.perspectiveTransform(points_np, H)
            except cv2.error as e:
                raise ValueError(f"Transformation failed: {str(e)}") from e

            # Convert back to list of [lon, lat] pairs
            geo_coords = transformed.reshape(-1, 2).tolist()

            # Close polygon if needed
            if geo_coords[0] != geo_coords[-1]:
                geo_coords.append(geo_coords[0])

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon" if len(geo_coords) > 2 else "LineString",
                    "coordinates": [geo_coords]
                },
                "properties": {
                    "id": f"{element_type}-{idx}-{sub_idx}",
                    "svg_type": element_type,
                    "fill": element.get('fill', 'none'),
                    "stroke": element.get('stroke', 'none')
                }
            })

    return features


# Original SVG parsing functions remain unchanged
# [Include the complete parse_svg() and calculate_bounds() from provided code]

def main():
    parser = argparse.ArgumentParser(
        description='Georeference SVG using control points via homography',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('svg_file', help='Path to SVG file')
    parser.add_argument('geojson_file', help='Path to GeoJSON control points')
    parser.add_argument('-o', '--output', default='output.geojson',
                        help='Output file path')

    args = parser.parse_args()

    try:
        # Read input files
        svg_content = Path(args.svg_file).read_text()
        geojson_data = json.loads(Path(args.geojson_file).read_text())

        # Extract control points
        svg_pts, geo_pts = parse_control_points(svg_content, geojson_data)

        # Calculate homography matrix
        H = calculate_homography(svg_pts, geo_pts)

        # Parse SVG elements
        svg_elements = parse_svg(svg_content)

        # Transform all elements
        features = transform_svg_elements(svg_elements, H)

        # Generate output
        output_data = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "control_points": list(svg_pts.keys()),
                "homography_matrix": H.tolist() if H is not None else None
            }
        }

        Path(args.output).write_text(json.dumps(output_data, indent=2))
        print(f"Successfully processed {len(features)} features")

    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)


if __name__ == "__main__":
    main()
