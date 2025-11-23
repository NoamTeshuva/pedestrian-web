#!/usr/bin/env python3
"""
Download land use data from OpenStreetMap for Israel.

Downloads OSM land use polygons, amenities, natural features, and buildings
for the entire country of Israel, divided into zones for manageable downloads.

Usage:
    # Download all land use data for Israel
    python scripts/download_israel_landuse.py --grid 20x10

    # Download specific feature types only
    python scripts/download_israel_landuse.py --grid 20x10 --features landuse amenities

    # Resume from specific zone
    python scripts/download_israel_landuse.py --grid 20x10 --start-zone 50
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
from shapely.geometry import box

# Add api directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'api'))

from feature_engineering.israel_weather_zones import generate_israel_weather_zones


def setup_logging():
    """Configure logging."""
    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / 'landuse_download.log'

    # Configure logging to both file and console
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='a'),
            logging.StreamHandler()
        ]
    )
    # Suppress OSMnx verbose logging
    logging.getLogger('osmnx').setLevel(logging.WARNING)

    logging.info(f"Logging to: {log_file}")


def download_landuse_for_zone(zone_geometry, zone_id: str, feature_types: list):
    """
    Download OSM land use features for a zone.

    Parameters
    ----------
    zone_geometry : shapely Polygon
        Zone boundary polygon
    zone_id : str
        Zone identifier
    feature_types : list
        List of feature types to download ('landuse', 'amenities', 'natural', 'buildings')

    Returns
    -------
    dict
        Dictionary mapping feature type to GeoDataFrame
    """
    results = {}

    try:
        # Get bounding box
        bounds = zone_geometry.bounds  # (minx, miny, maxx, maxy)
        west, south, east, north = bounds

        logging.info(f"  Downloading OSM features for {zone_id}...")
        logging.info(f"    Bbox: ({west:.4f}, {south:.4f}, {east:.4f}, {north:.4f})")

        # Define tags for each feature type
        tags_map = {
            'landuse': {'landuse': True},  # All land use types
            'amenities': {'amenity': True},  # Schools, hospitals, restaurants, shops, etc.
            'natural': {'natural': True},  # Parks, forests, water bodies
            'buildings': {'building': True},  # Building footprints
            'leisure': {'leisure': True},  # Parks, playgrounds, sports facilities
            'shop': {'shop': True},  # Retail shops
        }

        for feature_type in feature_types:
            if feature_type not in tags_map:
                logging.warning(f"  Unknown feature type: {feature_type}, skipping")
                continue

            try:
                logging.info(f"    Downloading {feature_type}...")

                # Download geometries using OSMnx
                gdf = ox.features_from_bbox(
                    bbox=(north, south, east, west),
                    tags=tags_map[feature_type]
                )

                if gdf is not None and len(gdf) > 0:
                    # Keep only polygon and multipolygon geometries
                    gdf = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]

                    if len(gdf) > 0:
                        logging.info(f"      [OK] Downloaded {len(gdf)} {feature_type} features")
                        results[feature_type] = gdf
                    else:
                        logging.info(f"      [SKIP] No polygon {feature_type} features found")
                else:
                    logging.info(f"      [SKIP] No {feature_type} features found")

            except Exception as e:
                logging.warning(f"      [FAIL] Failed to download {feature_type}: {e}")

        return results

    except Exception as e:
        logging.error(f"  [FAIL] Failed to download features for {zone_id}: {e}")
        return {}


def save_landuse_data(feature_gdfs: dict, output_path: Path, zone_id: str):
    """
    Save land use data to GPKG file.

    Parameters
    ----------
    feature_gdfs : dict
        Dictionary mapping feature type to GeoDataFrame
    output_path : Path
        Output file path
    zone_id : str
        Zone identifier
    """
    try:
        if not feature_gdfs:
            logging.warning(f"  [SKIP] No features to save for {zone_id}")
            return

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save each feature type as a separate layer in the GPKG
        total_features = 0
        for feature_type, gdf in feature_gdfs.items():
            try:
                # Select essential columns
                essential_cols = ['geometry']

                # Add common OSM tags if they exist
                for col in ['name', 'landuse', 'amenity', 'natural', 'building', 'leisure', 'shop']:
                    if col in gdf.columns:
                        essential_cols.append(col)

                # Keep only available columns
                available_cols = [col for col in essential_cols if col in gdf.columns]
                save_gdf = gdf[available_cols].copy()

                # Save to GPKG layer
                save_gdf.to_file(
                    output_path,
                    driver="GPKG",
                    layer=feature_type,
                    engine="pyogrio"
                )

                total_features += len(save_gdf)
                logging.info(f"      [OK] Saved {len(save_gdf)} {feature_type} features")

            except Exception as e:
                logging.error(f"      [FAIL] Failed to save {feature_type} layer: {e}")

        # Get file size
        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        logging.info(f"  [OK] Saved {total_features} total features to {output_path.name} ({file_size_mb:.2f} MB)")

    except Exception as e:
        logging.error(f"  [FAIL] Failed to save land use data for {zone_id}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Download OSM land use data for Israel weather zones"
    )
    parser.add_argument(
        '--grid',
        type=str,
        default='20x10',
        help='Grid size as "COLSxROWS" (e.g., "20x10" for 200 zones)'
    )
    parser.add_argument(
        '--start-zone',
        type=int,
        default=0,
        help='Start from this zone index (for resuming)'
    )
    parser.add_argument(
        '--features',
        nargs='+',
        default=['landuse', 'amenities', 'natural', 'leisure', 'shop', 'buildings'],
        help='Feature types to download (landuse, amenities, natural, leisure, shop, buildings)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/processed/israel/landuse',
        help='Output directory for land use files'
    )

    args = parser.parse_args()

    setup_logging()

    # Parse grid size
    try:
        cols, rows = map(int, args.grid.split('x'))
    except ValueError:
        logging.error("Invalid grid format. Use 'COLSxROWS' (e.g., '20x10')")
        return 1

    total_zones = cols * rows

    logging.info("=" * 80)
    logging.info("DOWNLOAD ISRAEL LAND USE DATA FROM OSM")
    logging.info("=" * 80)
    logging.info(f"Grid size: {cols}×{rows} = {total_zones} zones")
    logging.info(f"Feature types: {', '.join(args.features)}")
    logging.info(f"Output directory: {args.output_dir}")
    logging.info(f"Starting from zone: {args.start_zone}")
    logging.info("=" * 80)

    # Generate zones
    logging.info(f"\nGenerating {total_zones} weather zones...")
    zones_gdf = generate_israel_weather_zones(n_cols=cols, n_rows=rows)
    logging.info(f"[OK] Generated {len(zones_gdf)} zones")

    # Process each zone
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime.now()
    success_count = 0
    failed_zones = []

    for idx, zone in zones_gdf.iterrows():
        zone_idx = int(zone['zone_id'].split('_')[1])

        # Skip zones before start index
        if zone_idx < args.start_zone:
            continue

        zone_id = zone['zone_id']
        geometry = zone['geometry']

        logging.info(f"\n[{zone_idx + 1}/{total_zones}] Processing {zone_id}...")

        # Output file path
        output_file = output_dir / f"{zone_id}_landuse.gpkg"

        # Skip if already exists
        if output_file.exists():
            logging.info(f"  [SKIP] Already exists, skipping: {output_file.name}")
            success_count += 1
            continue

        # Download land use data
        feature_gdfs = download_landuse_for_zone(geometry, zone_id, args.features)

        if not feature_gdfs:
            logging.warning(f"  [SKIP] No features downloaded for {zone_id}")
            failed_zones.append(zone_id)
            continue

        # Save to GPKG
        save_landuse_data(feature_gdfs, output_file, zone_id)

        success_count += 1

        # Progress update
        elapsed = (datetime.now() - start_time).total_seconds()
        avg_time_per_zone = elapsed / (zone_idx - args.start_zone + 1)
        remaining_zones = total_zones - zone_idx - 1
        eta_seconds = avg_time_per_zone * remaining_zones
        eta_hours = eta_seconds / 3600

        logging.info(f"  Progress: {zone_idx + 1}/{total_zones} ({100*(zone_idx+1)/total_zones:.1f}%)")
        logging.info(f"  Avg time/zone: {avg_time_per_zone:.1f}s | ETA: {eta_hours:.1f}h")

        # Brief pause to avoid rate limiting
        time.sleep(2)

    # Summary
    total_time = (datetime.now() - start_time).total_seconds()
    total_hours = total_time / 3600

    logging.info("\n" + "=" * 80)
    logging.info("SUMMARY")
    logging.info("=" * 80)
    logging.info(f"Total zones: {total_zones}")
    logging.info(f"Successfully processed: {success_count}")
    logging.info(f"Failed/skipped: {len(failed_zones)}")
    logging.info(f"Total time: {total_hours:.2f} hours")

    if failed_zones:
        logging.info(f"\nFailed zones: {', '.join(failed_zones[:10])}")
        if len(failed_zones) > 10:
            logging.info(f"  ... and {len(failed_zones) - 10} more")

    # Calculate total storage
    total_size_mb = sum(
        f.stat().st_size for f in output_dir.glob("*.gpkg")
    ) / (1024 * 1024)
    logging.info(f"\nTotal storage: {total_size_mb:.1f} MB ({total_size_mb/1024:.2f} GB)")

    logging.info("\n" + "=" * 80)
    logging.info("NEXT STEPS")
    logging.info("=" * 80)
    logging.info("1. Upload land use data to Vultr:")
    logging.info(f"   python scripts/upload_landuse_to_vultr.py --grid {args.grid}")
    logging.info("2. Integrate land use features into feature engineering")
    logging.info("3. Retrain model with land use features")

    return 0


if __name__ == '__main__':
    sys.exit(main())
