#!/usr/bin/env python3
"""
Precompute NDVI and DEM rasters for each Israeli city.

Clips the national israel_ndvi_sentinel2.tif and israel_dem_copernicus30.tif
to each city's boundary and saves individual rasters for fast prediction.

Usage:
    # Process all cities
    python scripts/precompute_israel_city_rasters.py

    # Resume from specific city (alphabetical order)
    python scripts/precompute_israel_city_rasters.py --start-index 50

    # Process specific cities only
    python scripts/precompute_israel_city_rasters.py --cities tel_aviv haifa jerusalem

    # Dry run to see what would be processed
    python scripts/precompute_israel_city_rasters.py --dry-run
"""
import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime
import time

# Geospatial imports
try:
    import geopandas as gpd
    import rasterio
    from rasterio.mask import mask
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    import numpy as np
    GEOSPATIAL_AVAILABLE = True
except ImportError as e:
    print(f"Error: Missing required geospatial libraries: {e}")
    print("Install with: pip install geopandas rasterio")
    sys.exit(1)


def setup_logging():
    """Configure logging to file and console."""
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / 'city_raster_precomputation.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='a'),
            logging.StreamHandler()
        ]
    )

    logging.info(f"Logging to: {log_file}")


def load_city_boundaries(landuse_dir: Path) -> dict:
    """
    Load all city landuse boundaries.

    Parameters
    ----------
    landuse_dir : Path
        Directory containing city landuse GPKG files

    Returns
    -------
    dict
        City name -> GeoDataFrame mapping
    """
    city_boundaries = {}

    if not landuse_dir.exists():
        logging.error(f"Landuse directory not found: {landuse_dir}")
        return city_boundaries

    landuse_files = sorted(landuse_dir.glob("*_landuse.gpkg"))

    for landuse_file in landuse_files:
        city_name = landuse_file.stem.replace('_landuse', '')

        try:
            gdf = gpd.read_file(landuse_file)

            if len(gdf) == 0:
                logging.warning(f"  ⊙ Empty landuse file for {city_name}")
                continue

            # Get union of all landuse polygons as city boundary
            city_boundary = gdf.geometry.unary_union
            city_gdf = gpd.GeoDataFrame({'geometry': [city_boundary]}, crs=gdf.crs)

            city_boundaries[city_name] = city_gdf

        except Exception as e:
            logging.error(f"  ✗ Failed to load {city_name}: {e}")

    return city_boundaries


def clip_raster_to_boundary(raster_path: Path, boundary_gdf: gpd.GeoDataFrame,
                            output_path: Path, city_name: str, raster_type: str) -> bool:
    """
    Clip raster to city boundary and save.

    Parameters
    ----------
    raster_path : Path
        Path to source raster (NDVI or DEM)
    boundary_gdf : GeoDataFrame
        City boundary polygon(s)
    output_path : Path
        Output path for clipped raster
    city_name : str
        City name for logging
    raster_type : str
        'ndvi' or 'dem' for logging

    Returns
    -------
    bool
        True if successful, False otherwise
    """
    try:
        with rasterio.open(raster_path) as src:
            # Reproject boundary to raster CRS if needed
            if boundary_gdf.crs != src.crs:
                boundary_gdf = boundary_gdf.to_crs(src.crs)

            # Get the geometry in GeoJSON format
            shapes = [geom.__geo_interface__ for geom in boundary_gdf.geometry]

            # Clip the raster
            out_image, out_transform = mask(src, shapes, crop=True, nodata=src.nodata)

            # Check if clipped raster has any valid data
            if src.nodata is not None:
                valid_pixels = np.sum(out_image != src.nodata)
            else:
                valid_pixels = np.sum(~np.isnan(out_image))

            if valid_pixels == 0:
                logging.warning(f"    ⊙ No valid {raster_type.upper()} data for {city_name}")
                return False

            # Update metadata
            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "compress": "lzw",  # Compress to save space
                "tiled": True,      # Enable tiling for faster access
                "blockxsize": 256,
                "blockysize": 256
            })

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write clipped raster
            with rasterio.open(output_path, "w", **out_meta) as dest:
                dest.write(out_image)

            # Get file size
            file_size_kb = output_path.stat().st_size / 1024
            logging.info(f"    ✓ Saved {raster_type.upper()}: {output_path.name} ({file_size_kb:.1f} KB, {valid_pixels:,} valid pixels)")

            return True

    except Exception as e:
        logging.error(f"    ✗ Failed to clip {raster_type.upper()} for {city_name}: {e}")
        return False


def process_city(city_name: str, boundary_gdf: gpd.GeoDataFrame,
                ndvi_raster: Path, dem_raster: Path, output_dir: Path) -> dict:
    """
    Process a single city: clip both NDVI and DEM rasters.

    Parameters
    ----------
    city_name : str
        City name
    boundary_gdf : GeoDataFrame
        City boundary
    ndvi_raster : Path
        Path to national NDVI raster
    dem_raster : Path
        Path to national DEM raster
    output_dir : Path
        Base output directory

    Returns
    -------
    dict
        Processing results: {'ndvi': bool, 'dem': bool}
    """
    city_output_dir = output_dir / city_name

    results = {'ndvi': False, 'dem': False}

    # NDVI raster
    ndvi_output = city_output_dir / f"{city_name}_ndvi.tif"
    if ndvi_output.exists():
        logging.info(f"    ⊙ NDVI already exists, skipping")
        results['ndvi'] = True
    else:
        results['ndvi'] = clip_raster_to_boundary(
            ndvi_raster, boundary_gdf, ndvi_output, city_name, 'ndvi'
        )

    # DEM raster
    dem_output = city_output_dir / f"{city_name}_dem.tif"
    if dem_output.exists():
        logging.info(f"    ⊙ DEM already exists, skipping")
        results['dem'] = True
    else:
        results['dem'] = clip_raster_to_boundary(
            dem_raster, boundary_gdf, dem_output, city_name, 'dem'
        )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Precompute NDVI and DEM rasters for Israeli cities"
    )
    parser.add_argument(
        '--landuse-dir',
        type=str,
        default='data/processed/israel/cities_landuse',
        help='Directory containing city landuse files'
    )
    parser.add_argument(
        '--ndvi-raster',
        type=str,
        default='data/processed/israel/rasters/israel_ndvi_sentinel2.tif',
        help='Path to national NDVI raster'
    )
    parser.add_argument(
        '--dem-raster',
        type=str,
        default='data/processed/israel/rasters/israel_dem_copernicus30.tif',
        help='Path to national DEM raster'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/processed/israel/cities',
        help='Output directory for city rasters'
    )
    parser.add_argument(
        '--start-index',
        type=int,
        default=0,
        help='Start from this city index (alphabetical order, for resuming)'
    )
    parser.add_argument(
        '--cities',
        nargs='+',
        help='Process only these specific cities (names without _landuse suffix)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be processed without actually processing'
    )

    args = parser.parse_args()

    setup_logging()

    # Convert paths
    landuse_dir = Path(args.landuse_dir)
    ndvi_raster = Path(args.ndvi_raster)
    dem_raster = Path(args.dem_raster)
    output_dir = Path(args.output_dir)

    logging.info("=" * 80)
    logging.info("PRECOMPUTE ISRAEL CITY RASTERS")
    logging.info("=" * 80)
    logging.info(f"Landuse directory: {landuse_dir}")
    logging.info(f"NDVI raster: {ndvi_raster}")
    logging.info(f"DEM raster: {dem_raster}")
    logging.info(f"Output directory: {output_dir}")
    logging.info(f"Start index: {args.start_index}")
    if args.cities:
        logging.info(f"Filtering cities: {', '.join(args.cities)}")
    if args.dry_run:
        logging.info("DRY RUN MODE - No files will be created")
    logging.info("=" * 80)

    # Check source rasters exist
    if not ndvi_raster.exists():
        logging.error(f"NDVI raster not found: {ndvi_raster}")
        return 1
    if not dem_raster.exists():
        logging.error(f"DEM raster not found: {dem_raster}")
        return 1

    # Load city boundaries
    logging.info(f"\nLoading city boundaries from {landuse_dir}...")
    city_boundaries = load_city_boundaries(landuse_dir)

    if not city_boundaries:
        logging.error("No city boundaries loaded!")
        return 1

    logging.info(f"✓ Loaded {len(city_boundaries)} city boundaries")

    # Filter cities if specified
    if args.cities:
        filtered = {name: gdf for name, gdf in city_boundaries.items() if name in args.cities}
        if not filtered:
            logging.error(f"None of the specified cities found: {args.cities}")
            return 1
        city_boundaries = filtered
        logging.info(f"✓ Filtered to {len(city_boundaries)} specified cities")

    # Sort cities alphabetically for consistent ordering
    city_names = sorted(city_boundaries.keys())

    # Apply start index
    if args.start_index > 0:
        city_names = city_names[args.start_index:]
        logging.info(f"✓ Starting from city index {args.start_index}")

    total_cities = len(city_names)
    logging.info(f"\nProcessing {total_cities} cities...")
    logging.info("=" * 80)

    if args.dry_run:
        for idx, city_name in enumerate(city_names[:10]):
            logging.info(f"  [{idx+1}/{total_cities}] Would process: {city_name}")
        if total_cities > 10:
            logging.info(f"  ... and {total_cities - 10} more cities")
        logging.info("\nDry run complete. Run without --dry-run to process.")
        return 0

    # Process each city
    start_time = datetime.now()
    success_count = 0
    failed_cities = []

    for idx, city_name in enumerate(city_names):
        actual_idx = args.start_index + idx
        boundary_gdf = city_boundaries[city_name]

        logging.info(f"\n[{actual_idx + 1}/{len(city_boundaries) + args.start_index}] Processing {city_name}...")

        results = process_city(city_name, boundary_gdf, ndvi_raster, dem_raster, output_dir)

        if results['ndvi'] and results['dem']:
            success_count += 1
        elif not results['ndvi'] and not results['dem']:
            failed_cities.append(city_name)
        else:
            # Partial success
            success_count += 0.5

        # Progress update every 10 cities
        if (idx + 1) % 10 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            avg_time = elapsed / (idx + 1)
            remaining = total_cities - (idx + 1)
            eta_seconds = avg_time * remaining
            eta_minutes = eta_seconds / 60

            logging.info(f"\n  Progress: {idx + 1}/{total_cities} ({100*(idx+1)/total_cities:.1f}%)")
            logging.info(f"  Avg time/city: {avg_time:.1f}s | ETA: {eta_minutes:.1f} minutes")

    # Summary
    total_time = (datetime.now() - start_time).total_seconds()
    total_minutes = total_time / 60

    logging.info("\n" + "=" * 80)
    logging.info("SUMMARY")
    logging.info("=" * 80)
    logging.info(f"Total cities: {total_cities}")
    logging.info(f"Successfully processed: {success_count}")
    logging.info(f"Failed: {len(failed_cities)}")
    logging.info(f"Total time: {total_minutes:.1f} minutes ({total_time/3600:.2f} hours)")

    if failed_cities:
        logging.info(f"\nFailed cities: {', '.join(failed_cities[:20])}")
        if len(failed_cities) > 20:
            logging.info(f"  ... and {len(failed_cities) - 20} more")

    # Calculate total storage
    if output_dir.exists():
        total_size_mb = sum(
            f.stat().st_size for f in output_dir.rglob("*.tif")
        ) / (1024 * 1024)
        logging.info(f"\nTotal storage: {total_size_mb:.1f} MB")

        # Count files
        ndvi_files = len(list(output_dir.rglob("*_ndvi.tif")))
        dem_files = len(list(output_dir.rglob("*_dem.tif")))
        logging.info(f"Files created: {ndvi_files} NDVI, {dem_files} DEM")

    logging.info("\n" + "=" * 80)
    logging.info("NEXT STEPS")
    logging.info("=" * 80)
    logging.info("1. Upload city rasters to Vultr:")
    logging.info("   python scripts/upload_city_rasters_to_vultr.py")
    logging.info("2. Update environmental_features.py to use city-specific rasters")
    logging.info("3. Test predictions with new data")

    return 0 if len(failed_cities) == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
