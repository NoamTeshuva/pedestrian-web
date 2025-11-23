#!/usr/bin/env python3
"""List all contents in Vultr Object Storage bucket."""

import os
import sys

# Add parent directory to path to import storage_utils
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

    # List all files
    print("Listing all files in bucket...")
    all_files = storage.list_files(prefix="")

    if not all_files:
        print("No files found in bucket")
        return

    # Group by prefix
    prefixes = {}
    for file_key in all_files:
        parts = file_key.split('/')
        if len(parts) > 1:
            prefix = '/'.join(parts[:-1])
        else:
            prefix = "(root)"

        if prefix not in prefixes:
            prefixes[prefix] = []
        prefixes[prefix].append(file_key)

    # Display grouped by prefix
    print(f"\nFound {len(all_files)} total files\n")
    print("=" * 80)

    for prefix in sorted(prefixes.keys()):
        print(f"\n{prefix}/ ({len(prefixes[prefix])} files)")
        print("-" * 80)
        for file_key in sorted(prefixes[prefix])[:10]:
            print(f"  {file_key}")
        if len(prefixes[prefix]) > 10:
            print(f"  ... and {len(prefixes[prefix]) - 10} more files")

if __name__ == "__main__":
    main()
