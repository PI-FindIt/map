import cv2
import json
import geojson
import numpy as np
import argparse
import os
from pathlib import Path
from geojson import Feature, Point, LineString, FeatureCollection, dump


def get_extents(geojson_file):
    """Extracts N, E, S, W extents from GeoJSON file with GeometryCollection structure."""
    with open(geojson_file, 'r') as datafile:
        data = json.load(datafile)

    lats, lons = [], []
    geometries = [feature['geometry'] for feature in data['features']]

    for geom in geometries:
        coords = geom['coordinates']

        if geom['type'] == 'Point':
            lons.append(coords[0])
            lats.append(coords[1])
        # elif geom['type'] in ['Polygon', 'MultiPolygon', 'LineString']:
        #     # Handle both 2D and 3D coordinates
        #     def process_coords(coords):
        #         for coord in coords:
        #             if isinstance(coord[0], (list, tuple)):  # Nested array
        #                 process_coords(coord)
        #             else:
        #                 lons.append(coord[0])
        #                 lats.append(coord[1])
        #
        #     process_coords(coords)

    if not lats or not lons:
        return None

    return max(lats), max(lons), min(lats), min(lons)

def load_and_trim_image(image_path, output_cropped_path):
    """Loads, preprocesses, and saves cropped floor plan image."""
    im = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise FileNotFoundError(f"Could not load image at {image_path}")

    # Enhance line detection
    _, thresh = cv2.threshold(im, 240, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((1,1), np.uint8)
    dilated = cv2.dilate(thresh, kernel, iterations=1)

    # Find bounding box
    coords = cv2.findNonZero(dilated)
    if coords is None:
        raise ValueError("No detectable features found in the image")

    x, y, w, h = cv2.boundingRect(coords)
    cropped = dilated[y:y + h, x:x + w]

    # Always save the cropped image
    cv2.imwrite(str(output_cropped_path), cropped)
    print(f"Cropped image saved to {output_cropped_path}")

    return cropped, (w, h)


def process_walls(im, min_wall_area=100):
    """Detects and processes all walls including indoor partitions."""
    contours, _ = cv2.findContours(im, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    wall_data = []

    for contour in contours:
        if cv2.contourArea(contour) < min_wall_area:
            continue

        epsilon = 0.001 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        wall_data.append({
            'points': approx,
            'is_closed': cv2.isContourConvex(approx)
        })

    return wall_data


def convert_to_geojson(walls, size, extents, output_type='both'):
    """
    Convert wall data to GeoJSON features.
    output_type: 'points', 'lines', or 'both'
    """
    N, E, S, W = extents
    width, height = size

    # Calculate pixel-to-degree ratios
    deg_per_px_EW = (E - W) / width
    deg_per_px_NS = (N - S) / height

    features = []

    for wall in walls:
        coords = []
        for point in wall['points']:
            # Convert to original image coordinates
            px_x = point[0][0]
            px_y = point[0][1]

            # Convert to geographic coordinates
            lon = W + (px_x * deg_per_px_EW)
            lat = N - (px_y * deg_per_px_NS)
            coords.append((lon, lat))

        # Create features based on output type
        if output_type in ['lines', 'both'] and len(coords) >= 2:
            features.append(Feature(
                geometry=LineString(coords),
                properties={"type": "wall"}
            ))

        if output_type in ['points', 'both']:
            for coord in coords:
                features.append(Feature(
                    geometry=Point(coord),
                    properties={"type": "vertex"}
                ))

    return FeatureCollection(features)


def main():
    parser = argparse.ArgumentParser(description='Process floor plan image and generate GeoJSON.')
    parser.add_argument('image_path', type=str, help='Path to the floor plan image (PNG)')
    parser.add_argument('geojson_path', type=str, help='Path to the boundary GeoJSON file')
    parser.add_argument('-o', type=str, help='Output path')
    parser.add_argument('-m', type=int, default=100, help='Minimum wall area threshold')
    parser.add_argument('-t', type=str, default='both',
                        choices=['points', 'lines', 'both'],
                        help='Type of features to output: points, lines, or both')

    args = parser.parse_args()

    try:
        # Get input image directory and stem
        input_path = Path(args.image_path)
        input_stem = input_path.stem

        # Set default output paths if not provided
        if not args.o:
            args.o = "."

        # Process inputs
        extents = get_extents(args.geojson_path)
        cropped_im, cropped_size = load_and_trim_image(
            args.image_path,
            output_cropped_path=f"{args.o}/{input_stem}_cropped.png"
        )

        walls = process_walls(cropped_im, min_wall_area=args.m)

        # Generate GeoJSON
        feature_collection = convert_to_geojson(
            walls,
            cropped_size,
            extents,
            output_type=args.t
        )

        # Save output
        save = f"{args.o}/{input_stem}_output.geojson"
        with open(save, 'w') as f:

            dump(feature_collection, f)

        print(f"Successfully processed {args.image_path}")
        print(f"Results saved in {args.o}")

    except Exception as e:
        print(f"Error processing files: {str(e)}")
        exit(1)


if __name__ == "__main__":
    main()