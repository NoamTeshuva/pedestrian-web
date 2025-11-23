#!/usr/bin/env python3
"""List all files in project/ directory."""

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

# List all files in project/
project_files = storage.list_files('project/')

# Group by type
tif_files = [f for f in project_files if f.endswith('.tif')]
zip_files = [f for f in project_files if f.endswith('.zip')]
other_files = [f for f in project_files if not f.endswith('.tif') and not f.endswith('.zip')]

print(f'Total files in project/: {len(project_files)}')
print(f'  TIF files: {len(tif_files)}')
print(f'  ZIP files: {len(zip_files)}')
print(f'  Other files: {len(other_files)}')

print(f'\n=== TIF files (showing first 20) ===')
for f in sorted(tif_files)[:20]:
    print(f'  {f}')

print(f'\n=== ZIP files ===')
for f in sorted(zip_files):
    print(f'  {f}')

print(f'\n=== Looking for national rasters ===')
for f in project_files:
    if 'israel' in f.lower() or 'national' in f.lower():
        print(f'  {f}')
