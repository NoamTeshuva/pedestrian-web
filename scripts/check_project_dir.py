#!/usr/bin/env python3
"""Check project directory in Vultr."""

import sys
import os
from pathlib import Path

# Load .env file
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from storage_utils import get_vultr_storage

storage = get_vultr_storage()
if not storage:
    print('ERROR: Could not connect')
    sys.exit(1)

print('Checking specific paths...\n')

# Check the specific files the user mentioned
test_paths = [
    'project/assets/browser_images/browser_images_8.zip',
    'project/assets/browser_images/browser_images_9.zip',
    'raw/sentinel2/S2B_MSIL2A_20251031T081959_N0511_R121_T36RXU_20251031T104436.SAFE.zip',
    'data/processed/israel/rasters/israel_ndvi_sentinel2.tif',
    'data/processed/israel/rasters/israel_dem_copernicus30.tif',
    'project/israel_ndvi_sentinel2.tif',
    'project/israel_dem_copernicus30.tif',
    'project/assets/israel_ndvi_sentinel2.tif',
    'project/assets/israel_dem_copernicus30.tif',
]

for path in test_paths:
    exists = storage.file_exists(path)
    print(f'[{"YES" if exists else "NO "}] {path}')

# Try listing with different prefixes
print('\n' + '='*60)
print('Listing files with different prefixes...\n')

for prefix in ['project', 'project/', 'raw', 'raw/', 'data/processed/israel/rasters', 'data/processed/israel/rasters/']:
    files = storage.list_files(prefix)
    print(f'Prefix "{prefix}": {len(files)} files')
    if files and len(files) < 20:
        for f in files[:10]:
            print(f'  - {f}')
