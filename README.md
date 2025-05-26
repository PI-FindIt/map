# Indoor Mapping and Pathfinding System

## Overview

This repository contains tools and algorithms for building indoor mapping systems and implementing efficient pathfinding for indoor navigation. The system processes geospatial data and SVG floor plans to create navigable maps with pathfinding capabilities.

## Features

- **Geospatial Data Processing**: Convert between SVG coordinates and real-world geographic coordinates
- **Pathfinding Algorithms**: Implementations of efficient indoor navigation algorithms
- **Map Visualization**: Tools to visualize indoor maps and navigation paths
- **Data Conversion**: Utilities to transform between different geospatial formats

## Install required Python packages:
```bash
pip install -r requirements.txt
```

## Usage

### Georeferencing SVG Floor Plans

To convert an SVG floor plan to georeferenced GeoJSON:

```bash
python georeference.py floorplan.svg control_points.geojson -o output.geojson
```

### Example Control Points File

Create a GeoJSON file with reference points (example `control_points.geojson`):

```json
{
  "type": "FeatureCollection",
  "features": [
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-8.66044502, 40.63310366]}, "properties": {"id":0}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-8.66029085, 40.63306602]}, "properties": {"id":0}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-8.65977934, 40.63320307]}, "properties": {"id":0}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-8.65986813, 40.63325325]}, "properties": {"id":0}}
  ]
}
```

## Data Format Specifications

### Input Formats

1. **SVG Floor Plans**:
   - Should only contain `<line>` and `<path>` elements

2. **Control Points GeoJSON**:
   - Points that establish the geographic correspondence
   - Format:
     ```json
     {
       "type": "Feature",
       "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
       "properties": {"id": 0}
     }
     ```

### Output Formats

- **GeoJSON** with:
  - LineString features for walls/paths
  - Metadata about the transformation
