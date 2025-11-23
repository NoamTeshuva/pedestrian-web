#!/usr/bin/env python3
"""
Search for national rasters in Vultr bucket.
"""

import sys
import os

# Add api to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from storage_utils import get_vultr_storage

def main():
    storage = get_vultr_storage()

    if not storage:
        print('ERROR: Could not connect to Vultr storage')
        print('Make sure S3_* environment variables are set')
        return 1

    print('Searching for processed national rasters...\n')

    # Get all files in the bucket
    all_files = storage.list_files('')

    # Look for .tif files outside cities/ directory
    national_tifs = []
    for f in all_files:
        if f.endswith('.tif') and 'cities/' not in f:
            national_tifs.append(f)

    print(f'Found {len(national_tifs)} .tif files outside cities/ directory:\n')
    for f in sorted(national_tifs):
        print(f'  {f}')

    print('\n' + '='*60)

    # Look for files in data/processed/israel/ (not in cities/)
    israel_processed = []
    for f in all_files:
        if f.startswith('data/processed/israel/') and 'cities/' not in f:
            israel_processed.append(f)

    print(f'\nFound {len(israel_processed)} files in data/processed/israel/ (excluding cities/):\n')
    for f in sorted(israel_processed)[:50]:  # Limit to first 50
        print(f'  {f}')

    print('\n' + '='*60)

    # Look for any file with 'ndvi' or 'dem' in name (not in cities/)
    raster_files = []
    for f in all_files:
        fname = f.lower()
        if ('ndvi' in fname or 'dem' in fname) and 'cities/' not in fname:
            raster_files.append(f)

    print(f'\nFound {len(raster_files)} files with "ndvi" or "dem" in name (excluding cities/):\n')
    for f in sorted(raster_files):
        print(f'  {f}')

    print('\n' + '='*60)

    # Look in data/processed/ (top level, not israel/)
    data_processed = []
    for f in all_files:
        if f.startswith('data/processed/') and not f.startswith('data/processed/israel/'):
            data_processed.append(f)

    print(f'\nFound {len(data_processed)} files in data/processed/ (not in israel/):\n')
    for f in sorted(data_processed)[:50]:
        print(f'  {f}')

    return 0

if __name__ == '__main__':
    sys.exit(main())
