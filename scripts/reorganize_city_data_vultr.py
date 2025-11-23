#!/usr/bin/env python3
"""
Reorganize city data in Vultr - move landuse files into city directories.

Old structure:
  data/processed/israel/cities_landuse/{city}_landuse.gpkg
  data/processed/israel/cities/{city}/{city}_ndvi.tif
  data/processed/israel/cities/{city}/{city}_dem.tif

New structure:
  data/processed/israel/cities/{city}/{city}_landuse.gpkg
  data/processed/israel/cities/{city}/{city}_ndvi.tif
  data/processed/israel/cities/{city}/{city}_dem.tif
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

try:
    from storage_utils import VultrStorage
except ImportError as e:
    print(f"Error: Could not import storage_utils: {e}")
    sys.exit(1)

def main():
    # Initialize Vultr storage
    try:
        storage = VultrStorage()
        print(f"Connected to Vultr bucket: {storage.bucket_name}\n")
    except Exception as e:
        print(f"Failed to initialize Vultr storage: {e}")
        sys.exit(1)

    # Get all landuse files
    print("Finding landuse files...")
    landuse_files = storage.list_files(prefix="data/processed/israel/cities_landuse/")

    if not landuse_files:
        print("No landuse files found!")
        return 1

    print(f"Found {len(landuse_files)} landuse files\n")

    # Copy each landuse file to new location
    success_count = 0
    fail_count = 0
    skip_count = 0

    for idx, old_key in enumerate(landuse_files):
        # Extract city name from filename
        # e.g., "data/processed/israel/cities_landuse/tel_aviv_landuse.gpkg"
        filename = old_key.split('/')[-1]  # "tel_aviv_landuse.gpkg"
        city_name = filename.replace('_landuse.gpkg', '')  # "tel_aviv"

        # New location
        new_key = f"data/processed/israel/cities/{city_name}/{filename}"

        print(f"[{idx + 1}/{len(landuse_files)}] {city_name}")
        print(f"  From: {old_key}")
        print(f"  To:   {new_key}")

        # Check if already exists at new location
        if storage.file_exists(new_key):
            print(f"  [SKIP] Already exists at new location")
            skip_count += 1
            continue

        # Copy file (S3 copy operation within bucket)
        try:
            # Use boto3 copy_object to copy within the bucket
            storage.s3_client.copy_object(
                Bucket=storage.bucket_name,
                CopySource={'Bucket': storage.bucket_name, 'Key': old_key},
                Key=new_key
            )
            print(f"  [OK] Copied successfully")
            success_count += 1
        except Exception as e:
            print(f"  [FAIL] Copy failed: {e}")
            fail_count += 1

    # Summary
    print("\n" + "=" * 60)
    print("REORGANIZATION SUMMARY")
    print("=" * 60)
    print(f"Total files: {len(landuse_files)}")
    print(f"Copied: {success_count}")
    print(f"Already existed: {skip_count}")
    print(f"Failed: {fail_count}")
    print("=" * 60)

    # Verify new structure
    print("\nVerifying new structure...")

    # Sample a few cities to verify
    sample_cities = ['tel_aviv', 'haifa', 'jerusalem', 'beer_sheva', 'netanya']

    for city in sample_cities:
        prefix = f"data/processed/israel/cities/{city}/"
        files = storage.list_files(prefix=prefix)

        has_landuse = any('_landuse.gpkg' in f for f in files)
        has_ndvi = any('_ndvi.tif' in f for f in files)
        has_dem = any('_dem.tif' in f for f in files)

        status = "[OK]" if (has_landuse and has_ndvi and has_dem) else "[INCOMPLETE]"
        print(f"  {status} {city}: landuse={has_landuse}, ndvi={has_ndvi}, dem={has_dem}")

    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print("1. Verify the reorganization is correct")
    print("2. Test API with new structure")
    print("3. Delete old cities_landuse/ directory:")
    print("   python scripts/delete_old_landuse_dir.py")
    print("=" * 60)

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
