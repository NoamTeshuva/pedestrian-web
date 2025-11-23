#!/usr/bin/env python3
"""
Verify that city data reorganization in Vultr was successful.
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

    # Sample cities to verify
    sample_cities = ['tel_aviv', 'haifa', 'jerusalem', 'beer_sheva', 'netanya',
                     'ashdod', 'rishon_lezion', 'petah_tikva', 'holon', 'bnei_brak']

    print("Verifying new structure for sample cities...\n")

    complete_count = 0
    incomplete_count = 0

    for city in sample_cities:
        prefix = f"data/processed/israel/cities/{city}/"
        files = storage.list_files(prefix=prefix)

        has_landuse = any('_landuse.gpkg' in f for f in files)
        has_ndvi = any('_ndvi.tif' in f for f in files)
        has_dem = any('_dem.tif' in f for f in files)

        status = "[OK]" if (has_landuse and has_ndvi and has_dem) else "[INCOMPLETE]"

        if has_landuse and has_ndvi and has_dem:
            complete_count += 1
        else:
            incomplete_count += 1

        print(f"  {status} {city}: landuse={has_landuse}, ndvi={has_ndvi}, dem={has_dem}")

    print("\n" + "=" * 60)
    print(f"Sample verification: {complete_count}/{len(sample_cities)} cities complete")
    print("=" * 60)

    # Count total files in new structure
    print("\nCounting total files in new structure...")
    all_city_files = storage.list_files(prefix="data/processed/israel/cities/")

    landuse_count = sum(1 for f in all_city_files if '_landuse.gpkg' in f)
    ndvi_count = sum(1 for f in all_city_files if '_ndvi.tif' in f)
    dem_count = sum(1 for f in all_city_files if '_dem.tif' in f)

    print(f"  Landuse files: {landuse_count}")
    print(f"  NDVI files: {ndvi_count}")
    print(f"  DEM files: {dem_count}")
    print(f"  Total: {len(all_city_files)} files")

    print("\n" + "=" * 60)
    print("REORGANIZATION STATUS")
    print("=" * 60)

    if landuse_count == 277 and ndvi_count >= 276 and dem_count >= 276:
        print("SUCCESS! All files reorganized successfully.")
        print("\nNew structure:")
        print("  data/processed/israel/cities/{city}/")
        print("    - {city}_landuse.gpkg")
        print("    - {city}_ndvi.tif")
        print("    - {city}_dem.tif")
        print("\nNext steps:")
        print("1. Update API code to use new file structure")
        print("2. Test API with new structure")
        print("3. Delete old cities_landuse/ directory")
        return 0
    else:
        print("WARNING! Some files may be missing.")
        print(f"Expected: 277 landuse, 276+ NDVI, 276+ DEM")
        print(f"Found: {landuse_count} landuse, {ndvi_count} NDVI, {dem_count} DEM")
        return 1

if __name__ == "__main__":
    sys.exit(main())
