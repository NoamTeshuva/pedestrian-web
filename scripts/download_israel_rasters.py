#!/usr/bin/env python3
"""Download NDVI and DEM rasters from Vultr Object Storage."""

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
        print(f"Connected to Vultr bucket: {storage.bucket_name}")
    except Exception as e:
        print(f"Failed to initialize Vultr storage: {e}")
        sys.exit(1)

    # Define downloads
    downloads = [
        {
            'object_key': 'project/data/processed/israel/rasters/israel_ndvi_sentinel2.tif',
            'local_path': 'data/processed/israel/rasters/israel_ndvi_sentinel2.tif'
        },
        {
            'object_key': 'project/data/processed/israel/rasters/israel_dem_copernicus30.tif',
            'local_path': 'data/processed/israel/rasters/israel_dem_copernicus30.tif'
        }
    ]

    # Create output directory
    output_dir = Path('data/processed/israel/rasters')
    output_dir.mkdir(parents=True, exist_ok=True)

    # Download each file
    for item in downloads:
        object_key = item['object_key']
        local_path = item['local_path']

        # Check if already exists
        if Path(local_path).exists():
            file_size_mb = Path(local_path).stat().st_size / (1024 * 1024)
            print(f"[OK] Already exists: {local_path} ({file_size_mb:.1f} MB)")
            continue

        print(f"\nDownloading: {object_key}")
        print(f"         to: {local_path}")

        success = storage.download_file(object_key, local_path)

        if success:
            file_size_mb = Path(local_path).stat().st_size / (1024 * 1024)
            print(f"[OK] Downloaded: {local_path} ({file_size_mb:.1f} MB)")
        else:
            print(f"[FAIL] Failed to download: {object_key}")
            return 1

    print("\n" + "=" * 50)
    print("All rasters downloaded successfully!")
    print("=" * 50)
    return 0

if __name__ == '__main__':
    sys.exit(main())
