#!/usr/bin/env python3
"""
israel_weather_zones.py

Defines weather zones for Israel to enable precomputed weather profiles.
Divides Israel into ~50 grid cells, each with a unique zone_id.

This module provides:
- Generation of weather zone polygons covering Israel
- Loading/saving of zone definitions to GeoPackage
- Spatial lookup to map coordinates to zones
"""
import logging
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box
from pathlib import Path
from typing import Optional, Tuple
import os


# Israel bounding box in WGS84 (lon, lat)
# Covers from Mediterranean coast to Jordan valley, north to south
ISRAEL_BOUNDS = {
    'west': 34.2,    # Western coast (Mediterranean)
    'east': 35.9,    # Jordan Valley
    'south': 29.4,   # Eilat region
    'north': 33.3    # Northern border
}


def get_israel_bounds() -> Tuple[float, float, float, float]:
    """
    Get bounding box for Israel.

    Returns
    -------
    tuple
        (west, south, east, north) in EPSG:4326 (WGS84)
    """
    return (
        ISRAEL_BOUNDS['west'],
        ISRAEL_BOUNDS['south'],
        ISRAEL_BOUNDS['east'],
        ISRAEL_BOUNDS['north']
    )


def is_in_israel(lat: float, lon: float) -> bool:
    """
    Check if a point falls within Israel's bounding box.

    Parameters
    ----------
    lat : float
        Latitude in decimal degrees
    lon : float
        Longitude in decimal degrees

    Returns
    -------
    bool
        True if point is within Israel bounds
    """
    bounds = get_israel_bounds()
    return (bounds[0] <= lon <= bounds[2] and
            bounds[1] <= lat <= bounds[3])


def generate_israel_weather_zones(n_cols: int = 10, n_rows: int = 5) -> gpd.GeoDataFrame:
    """
    Generate a regular grid of weather zones covering Israel.

    Creates approximately 50 zones (10 x 5 grid) that cover Israel's area.
    Each zone represents a region with similar weather patterns.

    Parameters
    ----------
    n_cols : int
        Number of grid columns (longitude divisions)
    n_rows : int
        Number of grid rows (latitude divisions)

    Returns
    -------
    GeoDataFrame
        Zones with columns: zone_id, geometry
    """
    logging.info(f"Generating {n_cols}x{n_rows} weather zones for Israel")

    bounds = get_israel_bounds()
    west, south, east, north = bounds

    # Calculate cell dimensions
    lon_step = (east - west) / n_cols
    lat_step = (north - south) / n_rows

    zones = []
    zone_id_counter = 0

    for row in range(n_rows):
        for col in range(n_cols):
            # Calculate cell bounds
            cell_west = west + col * lon_step
            cell_east = west + (col + 1) * lon_step
            cell_south = south + row * lat_step
            cell_north = south + (row + 1) * lat_step

            # Create polygon
            cell_polygon = box(cell_west, cell_south, cell_east, cell_north)

            # Generate zone ID
            zone_id = f"IL_{zone_id_counter:03d}"

            zones.append({
                'zone_id': zone_id,
                'geometry': cell_polygon,
                'row': row,
                'col': col,
                'center_lon': (cell_west + cell_east) / 2,
                'center_lat': (cell_south + cell_north) / 2
            })

            zone_id_counter += 1

    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame(zones, crs="EPSG:4326")

    logging.info(f"Generated {len(gdf)} weather zones for Israel")
    return gdf


def save_israel_weather_zones(gdf: gpd.GeoDataFrame, output_path: str) -> None:
    """
    Save weather zones to GeoPackage.

    Parameters
    ----------
    gdf : GeoDataFrame
        Weather zones to save
    output_path : str
        Path to output .gpkg file
    """
    # Ensure directory exists
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save to GeoPackage
    gdf.to_file(output_path, driver="GPKG", layer="israel_weather_zones")
    logging.info(f"Saved {len(gdf)} weather zones to {output_path}")


def load_israel_weather_zones(zones_path: Optional[str] = None,
                              layer: str = "israel_weather_zones") -> gpd.GeoDataFrame:
    """
    Load Israel weather zones from GeoPackage or generate if missing.

    Parameters
    ----------
    zones_path : str, optional
        Path to zones .gpkg file. If None, uses default location.
    layer : str, optional
        Layer name in GPKG file. Default is "israel_weather_zones".

    Returns
    -------
    GeoDataFrame
        Weather zones with zone_id and geometry
    """
    # Default path in S3-compatible structure
    if zones_path is None:
        # Try to find zones file in common locations
        possible_paths = [
            "data/processed/israel/israel_weather_zones.gpkg",
            "../data/processed/israel/israel_weather_zones.gpkg",
            "../../data/processed/israel/israel_weather_zones.gpkg"
        ]

        for path in possible_paths:
            if os.path.exists(path):
                zones_path = path
                break

    # Load if exists
    if zones_path and os.path.exists(zones_path):
        logging.info(f"Loading weather zones from {zones_path}")
        return gpd.read_file(zones_path, layer=layer)

    # Generate if missing
    logging.warning(f"Weather zones file not found at {zones_path}. Generating new zones.")
    gdf = generate_israel_weather_zones()

    # Try to save for future use
    if zones_path:
        try:
            save_israel_weather_zones(gdf, zones_path)
        except Exception as e:
            logging.warning(f"Could not save zones to {zones_path}: {e}")

    return gdf


def find_zone_for_point(zones_gdf: gpd.GeoDataFrame,
                        point_geom: Point) -> Optional[str]:
    """
    Find the zone_id that contains a given point.

    If no direct intersection, finds the nearest zone.

    Parameters
    ----------
    zones_gdf : GeoDataFrame
        Weather zones with zone_id and geometry
    point_geom : Point
        Shapely Point geometry in EPSG:4326

    Returns
    -------
    str or None
        zone_id of containing/nearest zone, or None if not found
    """
    # Ensure CRS match
    if zones_gdf.crs and zones_gdf.crs != "EPSG:4326":
        zones_gdf = zones_gdf.to_crs("EPSG:4326")

    # Try direct intersection first
    containing_zones = zones_gdf[zones_gdf.geometry.contains(point_geom)]
    if len(containing_zones) > 0:
        return containing_zones.iloc[0]['zone_id']

    # Fallback: find nearest zone centroid
    try:
        zones_gdf = zones_gdf.copy()
        zones_gdf['distance'] = zones_gdf.geometry.centroid.distance(point_geom)
        nearest_zone = zones_gdf.loc[zones_gdf['distance'].idxmin()]
        logging.debug(f"Point not in any zone, using nearest zone: {nearest_zone['zone_id']}")
        return nearest_zone['zone_id']
    except Exception as e:
        logging.error(f"Failed to find zone for point: {e}")
        return None


def find_zone_for_geometry(zones_gdf: gpd.GeoDataFrame,
                           geometry) -> Optional[str]:
    """
    Find the zone_id for a given geometry (uses centroid).

    Parameters
    ----------
    zones_gdf : GeoDataFrame
        Weather zones with zone_id and geometry
    geometry : shapely geometry
        Any shapely geometry (Point, LineString, Polygon, etc.)

    Returns
    -------
    str or None
        zone_id of containing/nearest zone, or None if not found
    """
    # Get centroid
    centroid = geometry.centroid

    # Create Point if needed
    if not isinstance(centroid, Point):
        centroid = Point(centroid.x, centroid.y)

    return find_zone_for_point(zones_gdf, centroid)


if __name__ == "__main__":
    # Test zone generation and lookup
    logging.basicConfig(level=logging.INFO)

    print("\n=== Generating Israel Weather Zones ===")
    zones = generate_israel_weather_zones()
    print(f"Generated {len(zones)} zones")
    print(f"\nFirst 5 zones:")
    print(zones.head())

    print("\n=== Testing Zone Lookup ===")
    # Test locations in Israel
    test_locations = [
        ("Tel Aviv", 32.0853, 34.7818),
        ("Jerusalem", 31.7683, 35.2137),
        ("Haifa", 32.7940, 34.9896),
        ("Beer Sheva", 31.2518, 34.7913),
        ("Eilat", 29.5577, 34.9519)
    ]

    for name, lat, lon in test_locations:
        point = Point(lon, lat)
        zone_id = find_zone_for_point(zones, point)
        print(f"{name:15s} ({lat:.4f}, {lon:.4f}) → Zone {zone_id}")

    print("\n=== Testing is_in_israel() ===")
    print(f"Tel Aviv: {is_in_israel(32.0853, 34.7818)}")  # Should be True
    print(f"Paris: {is_in_israel(48.8566, 2.3522)}")      # Should be False
    print(f"Cairo: {is_in_israel(30.0444, 31.2357)}")     # Should be False

    # Save to file for manual inspection
    output_path = "test_israel_weather_zones.gpkg"
    save_israel_weather_zones(zones, output_path)
    print(f"\nSaved zones to {output_path}")
