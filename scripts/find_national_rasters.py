#!/usr/bin/env python3
"""Find national/processed rasters in Vultr."""

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

print('Searching for national rasters...\n')

all_files = storage.list_files('')

# Find all .tif files NOT in cities/
tifs_outside_cities = [f for f in all_files if f.endswith('.tif') and 'cities/' not in f]

print(f'=== TIF files outside cities/ ({len(tifs_outside_cities)}) ===')
for f in sorted(tifs_outside_cities):
    print(f'  {f}')

# Find all files in data/processed/israel/ NOT in cities/
israel_processed = [f for f in all_files if f.startswith('data/processed/israel/') and 'cities/' not in f]

print(f'\n=== Files in data/processed/israel/ excluding cities/ ({len(israel_processed)}) ===')
for f in sorted(israel_processed)[:100]:
    print(f'  {f}')

# Find files with 'ndvi' or 'dem' NOT in cities/
rasters = [f for f in all_files if ('ndvi' in f.lower() or 'dem' in f.lower()) and 'cities/' not in f]

print(f'\n=== Files with ndvi/dem NOT in cities/ ({len(rasters)}) ===')
for f in sorted(rasters):
    print(f'  {f}')

# Find files in data/processed/ NOT in israel/
other_processed = [f for f in all_files if f.startswith('data/processed/') and not f.startswith('data/processed/israel/')]

print(f'\n=== Files in data/processed/ NOT in israel/ ({len(other_processed)}) ===')
for f in sorted(other_processed)[:100]:
    print(f'  {f}')

# Find all files in raw/ directory
raw_files = [f for f in all_files if f.startswith('raw/')]

print(f'\n=== Files in raw/ directory ({len(raw_files)}) ===')
for f in sorted(raw_files):
    print(f'  {f}')

# Search for any file with 'israel' in the name (case insensitive)
israel_files = [f for f in all_files if 'israel' in f.lower() and 'cities/' not in f]

print(f'\n=== Files with "israel" in name (excluding cities/) ({len(israel_files)}) ===')
for f in sorted(israel_files)[:100]:
    print(f'  {f}')

# Check for specific files the user mentioned
specific_files = [
    'raw/sentinel2/S2B_MSIL2A_20251031T081959_N0511_R121_T36RXU_20251031T104436.SAFE.zip',
    'project/assets/browser_images/browser_images_8.zip',
    'project/assets/browser_images/browser_images_9.zip'
]

print(f'\n=== Checking specific files ===')
for f in specific_files:
    exists = storage.file_exists(f)
    print(f'  [{("EXISTS" if exists else "NOT FOUND")}] {f}')

# Find all files in project/ directory
project_files = [f for f in all_files if f.startswith('project/')]

print(f'\n=== Files in project/ directory ({len(project_files)}) ===')
for f in sorted(project_files):
    print(f'  {f}')

# List ALL files to see everything
print(f'\n=== COMPLETE FILE LIST (first 200) ===')
for i, f in enumerate(sorted(all_files)[:200]):
    print(f'  [{i+1}] {f}')

# Find all sentinel2 files
sentinel_files = [f for f in all_files if 'sentinel' in f.lower()]

print(f'\n=== Files with "sentinel" in name ({len(sentinel_files)}) ===')
for f in sorted(sentinel_files)[:20]:
    print(f'  {f}')
