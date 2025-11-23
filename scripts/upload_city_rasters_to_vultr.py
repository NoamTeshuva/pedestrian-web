#!/usr/bin/env python3
"""
Upload city-specific NDVI and DEM rasters to Vultr Object Storage.

Usage:
    # Set environment variables first
    export S3_ACCESS_KEY="your-access-key"
    export S3_SECRET_KEY="your-secret-key"
    export S3_ENDPOINT="https://ams1.vultrobjects.com"
    export S3_BUCKET="pedestrian-data-prod"

    # Run script
    python scripts/upload_city_rasters_to_vultr.py

    # Resume from specific city
    python scripts/upload_city_rasters_to_vultr.py --start-index 100

    # Verify only
    python scripts/upload_city_rasters_to_vultr.py --verify-only
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add parent directory to path to import storage_utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

try:
    from storage_utils import VultrStorage
except ImportError as e:
    print(f"Error: Could not import storage_utils: {e}")
    print("Make sure you're running from the project root and boto3 is installed:")
    print("  pip install boto3")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def find_city_rasters(cities_dir: str = "data/processed/israel/cities") -> dict:
    """
    Find all city raster files.

    Returns:
        Dict mapping city name -> {'ndvi': path, 'dem': path}
    """
    cities_path = Path(cities_dir)
    if not cities_path.exists():
        logger.error(f"Cities directory not found: {cities_dir}")
        return {}

    city_rasters = {}

    for city_dir in sorted(cities_path.iterdir()):
        if not city_dir.is_dir():
            continue

        city_name = city_dir.name
        ndvi_file = city_dir / f"{city_name}_ndvi.tif"
        dem_file = city_dir / f"{city_name}_dem.tif"

        if ndvi_file.exists() or dem_file.exists():
            city_rasters[city_name] = {
                'ndvi': str(ndvi_file) if ndvi_file.exists() else None,
                'dem': str(dem_file) if dem_file.exists() else None
            }

    return city_rasters


def upload_city_rasters(storage: VultrStorage, city_rasters: dict,
                         s3_prefix: str, start_index: int = 0) -> tuple[int, int]:
    """
    Upload city rasters to Vultr.

    Args:
        storage: VultrStorage instance
        city_rasters: Dict of city name -> {'ndvi': path, 'dem': path}
        s3_prefix: S3 prefix (e.g., "data/processed/israel/cities")
        start_index: Start from this city index

    Returns:
        Tuple of (successful_count, failed_count)
    """
    success_count = 0
    fail_count = 0

    city_names = sorted(city_rasters.keys())
    if start_index > 0:
        city_names = city_names[start_index:]

    total_cities = len(city_names)

    for idx, city_name in enumerate(city_names):
        actual_idx = start_index + idx
        rasters = city_rasters[city_name]

        logger.info(f"\n[{actual_idx + 1}/{start_index + total_cities}] Uploading {city_name}...")

        city_success = True

        # Upload NDVI
        if rasters['ndvi']:
            ndvi_path = rasters['ndvi']
            object_key = f"{s3_prefix}/{city_name}/{city_name}_ndvi.tif"

            # Check if already exists
            if storage.file_exists(object_key):
                logger.info(f"  [SKIP] NDVI already exists: {object_key}")
            else:
                file_size_mb = os.path.getsize(ndvi_path) / (1024 * 1024)
                logger.info(f"  Uploading NDVI ({file_size_mb:.2f} MB)...")

                if storage.upload_file(ndvi_path, object_key):
                    logger.info(f"  [OK] NDVI uploaded")
                else:
                    logger.error(f"  [FAIL] Failed to upload NDVI")
                    city_success = False

        # Upload DEM
        if rasters['dem']:
            dem_path = rasters['dem']
            object_key = f"{s3_prefix}/{city_name}/{city_name}_dem.tif"

            # Check if already exists
            if storage.file_exists(object_key):
                logger.info(f"  [SKIP] DEM already exists: {object_key}")
            else:
                file_size_kb = os.path.getsize(dem_path) / 1024
                logger.info(f"  Uploading DEM ({file_size_kb:.1f} KB)...")

                if storage.upload_file(dem_path, object_key):
                    logger.info(f"  [OK] DEM uploaded")
                else:
                    logger.error(f"  [FAIL] Failed to upload DEM")
                    city_success = False

        if city_success:
            success_count += 1
        else:
            fail_count += 1

        # Progress update every 20 cities
        if (idx + 1) % 20 == 0:
            logger.info(f"\n  Progress: {idx + 1}/{total_cities} ({100*(idx+1)/total_cities:.1f}%)")
            logger.info(f"  Success: {success_count}, Failed: {fail_count}")

    return success_count, fail_count


def verify_uploads(storage: VultrStorage, s3_prefix: str) -> None:
    """List uploaded city rasters to verify."""
    logger.info("\nVerifying uploads...")
    files = storage.list_files(prefix=s3_prefix)

    if not files:
        logger.warning(f"No files found in bucket under '{s3_prefix}' prefix")
        return

    # Count by type
    ndvi_count = sum(1 for f in files if '_ndvi.tif' in f)
    dem_count = sum(1 for f in files if '_dem.tif' in f)

    logger.info(f"Found {len(files)} total files:")
    logger.info(f"  - {ndvi_count} NDVI rasters")
    logger.info(f"  - {dem_count} DEM rasters")

    # Show sample
    logger.info(f"\nSample files:")
    for file_key in sorted(files)[:10]:
        logger.info(f"  {file_key}")
    if len(files) > 10:
        logger.info(f"  ... and {len(files) - 10} more files")


def main():
    parser = argparse.ArgumentParser(
        description="Upload city rasters to Vultr Object Storage"
    )
    parser.add_argument(
        '--cities-dir',
        type=str,
        default='data/processed/israel/cities',
        help='Directory containing city rasters'
    )
    parser.add_argument(
        '--s3-prefix',
        type=str,
        default='data/processed/israel/cities',
        help='S3 prefix for uploads (default: data/processed/israel/cities)'
    )
    parser.add_argument(
        '--start-index',
        type=int,
        default=0,
        help='Start from this city index (for resuming)'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify existing uploads, do not upload'
    )
    parser.add_argument(
        '--skip-confirmation',
        action='store_true',
        help='Skip upload confirmation prompt'
    )

    args = parser.parse_args()

    # Check for required environment variables
    required_vars = ['S3_ACCESS_KEY', 'S3_SECRET_KEY', 'S3_ENDPOINT', 'S3_BUCKET']
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("\nSet them with:")
        logger.error("  export S3_ACCESS_KEY='your-access-key'")
        logger.error("  export S3_SECRET_KEY='your-secret-key'")
        logger.error("  export S3_ENDPOINT='https://ams1.vultrobjects.com'")
        logger.error("  export S3_BUCKET='pedestrian-data-prod'")
        sys.exit(1)

    # Initialize Vultr storage
    try:
        storage = VultrStorage()
        logger.info(f"Connected to Vultr bucket: {storage.bucket_name}")
    except Exception as e:
        logger.error(f"Failed to initialize Vultr storage: {e}")
        sys.exit(1)

    # Verify only mode
    if args.verify_only:
        verify_uploads(storage, args.s3_prefix)
        return

    # Find all city rasters
    logger.info(f"\nFinding city rasters in {args.cities_dir}...")
    city_rasters = find_city_rasters(args.cities_dir)

    if not city_rasters:
        logger.error("No city rasters found!")
        logger.error("Make sure you've run precompute_israel_city_rasters.py first")
        sys.exit(1)

    logger.info(f"Found rasters for {len(city_rasters)} cities")

    # Calculate total size
    total_size_mb = 0
    total_files = 0
    for rasters in city_rasters.values():
        if rasters['ndvi']:
            total_size_mb += os.path.getsize(rasters['ndvi']) / (1024 * 1024)
            total_files += 1
        if rasters['dem']:
            total_size_mb += os.path.getsize(rasters['dem']) / (1024 * 1024)
            total_files += 1

    logger.info(f"Total files to upload: {total_files}")
    logger.info(f"Total size: {total_size_mb:.1f} MB")
    logger.info(f"S3 prefix: {args.s3_prefix}")
    if args.start_index > 0:
        logger.info(f"Starting from city index: {args.start_index}")

    # Confirm upload
    if not args.skip_confirmation:
        response = input("\nProceed with upload? [y/N]: ")
        if response.lower() != 'y':
            logger.info("Upload cancelled")
            return

    # Upload rasters
    logger.info("\nStarting upload...")
    success, failed = upload_city_rasters(storage, city_rasters, args.s3_prefix, args.start_index)

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info(f"Upload complete: {success} succeeded, {failed} failed")
    logger.info("=" * 50)

    # Verify
    verify_uploads(storage, args.s3_prefix)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
