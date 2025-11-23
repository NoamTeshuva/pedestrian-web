#!/usr/bin/env python3
"""
Download land use data using a dense grid covering all of Israel.

Creates overlapping circular queries across Israel to ensure complete coverage.
Much more comprehensive than city-based approach.

Usage:
    python scripts/download_israel_landuse_grid.py --spacing 5000
"""
import sys
import os
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime
import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point
import numpy as np

# Add api directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'api'))

from feature_engineering.israel_weather_zones import get_israel_bounds


def setup_logging():
    """Configure logging."""
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / 'grid_landuse_download.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='a'),
            logging.StreamHandler()
        ]
    )
    logging.getLogger('osmnx').setLevel(logging.WARNING)
    logging.info(f"Logging to: {log_file}")


def generate_grid_points(spacing_meters: int = 5000):
    """
    Generate grid of points covering Israel.

    Parameters
    ----------
    spacing_meters : int
        Distance between grid points in meters (~5km recommended)

    Returns
    -------
    list of dict
        Grid points with lat, lon, id
    """
    west, south, east, north = get_israel_bounds()

    # Convert spacing to degrees (approximate)
    # 1 degree latitude ≈ 111 km
    # 1 degree longitude ≈ 111 km * cos(latitude)
    avg_lat = (north + south) / 2
    lat_spacing = spacing_meters / 111000
    lon_spacing = spacing_meters / (111000 * np.cos(np.radians(avg_lat)))

    # Generate grid
    lats = np.arange(south, north, lat_spacing)
    lons = np.arange(west, east, lon_spacing)

    grid_points = []
    point_id = 0

    for lat in lats:
        for lon in lons:
            grid_points.append({
                'id': f'grid_{point_id:04d}',
                'lat': lat,
                'lon': lon
            })
            point_id += 1

    logging.info(f"Generated {len(grid_points)} grid points covering Israel")
    logging.info(f"Spacing: ~{spacing_meters/1000:.1f} km")
    logging.info(f"Grid: {len(lats)} rows × {len(lons)} cols")

    return grid_points


def download_grid_point_landuse(point_id: str, lat: float, lon: float, radius: int):
    """
    Download landuse data for a grid point.

    Parameters
    ----------
    point_id : str
        Grid point identifier
    lat : float
        Latitude
    lon : float
        Longitude
    radius : int
        Radius in meters

    Returns
    -------
    GeoDataFrame or None
        Landuse features
    """
    try:
        # Download from circular area
        gdf = ox.features_from_point(
            center_point=(lat, lon),
            dist=radius,
            tags={'landuse': True}
        )

        if gdf is not None and len(gdf) > 0:
            # Keep only polygon geometries
            gdf = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]

            if len(gdf) > 0:
                return gdf

        return None

    except Exception as e:
        # Silently skip empty areas (many grid points will be in sea/desert)
        return None


def save_grid_landuse(gdf: gpd.GeoDataFrame, output_path: Path, point_id: str):
    """Save grid point landuse data to GPKG."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Select essential columns
        essential_cols = ['geometry', 'landuse']
        for col in ['name', 'amenity', 'natural', 'leisure']:
            if col in gdf.columns:
                essential_cols.append(col)

        available_cols = [col for col in essential_cols if col in gdf.columns]
        save_gdf = gdf[available_cols].copy()

        # Save to GPKG
        save_gdf.to_file(output_path, driver="GPKG", layer="landuse", engine="pyogrio")

    except Exception as e:
        logging.error(f"    [FAIL] Failed to save {point_id}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Download OSM land use data using grid coverage of Israel"
    )
    parser.add_argument(
        '--spacing',
        type=int,
        default=5000,
        help='Spacing between grid points in meters (default: 5000m = 5km)'
    )
    parser.add_argument(
        '--radius',
        type=int,
        default=3000,
        help='Radius for each query in meters (default: 3000m = 3km)'
    )
    parser.add_argument(
        '--start-index',
        type=int,
        default=0,
        help='Start from this grid point index (for resuming)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/processed/israel/grid_landuse',
        help='Output directory'
    )

    args = parser.parse_args()

    setup_logging()

    logging.info("=" * 80)
    logging.info("DOWNLOAD LANDUSE FOR ISRAEL - GRID COVERAGE")
    logging.info("=" * 80)
    logging.info(f"Grid spacing: {args.spacing}m ({args.spacing/1000:.1f} km)")
    logging.info(f"Query radius: {args.radius}m ({args.radius/1000:.1f} km)")
    logging.info(f"Starting from index: {args.start_index}")
    logging.info("=" * 80)

    # Generate grid
    grid_points = generate_grid_points(args.spacing)
    total_points = len(grid_points)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime.now()
    success_count = 0
    empty_count = 0

    for i, point in enumerate(grid_points):
        if i < args.start_index:
            continue

        point_id = point['id']
        lat = point['lat']
        lon = point['lon']

        if (i + 1) % 50 == 0:
            logging.info(f"\n[{i+1}/{total_points}] Processing {point_id} ({lat:.4f}, {lon:.4f})...")

        output_file = output_dir / f"{point_id}_landuse.gpkg"

        # Skip if exists
        if output_file.exists():
            success_count += 1
            continue

        # Download
        gdf = download_grid_point_landuse(point_id, lat, lon, args.radius)

        if gdf is not None and len(gdf) > 0:
            save_grid_landuse(gdf, output_file, point_id)
            success_count += 1

            if (i + 1) % 50 == 0:
                logging.info(f"    [OK] {len(gdf)} features")
        else:
            empty_count += 1

        # Brief pause every 10 queries
        if i % 10 == 0:
            time.sleep(0.5)

    # Summary
    elapsed = (datetime.now() - start_time).total_seconds() / 60

    logging.info("\n" + "=" * 80)
    logging.info("SUMMARY")
    logging.info("=" * 80)
    logging.info(f"Total grid points: {total_points}")
    logging.info(f"Successfully processed: {success_count}")
    logging.info(f"Empty (sea/desert): {empty_count}")
    logging.info(f"Total time: {elapsed:.1f} minutes")

    # Calculate total storage
    total_size_mb = sum(
        f.stat().st_size for f in output_dir.glob("*.gpkg")
    ) / (1024 * 1024)
    logging.info(f"Total storage: {total_size_mb:.1f} MB")

    return 0


if __name__ == '__main__':
    sys.exit(main())
