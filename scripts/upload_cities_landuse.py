#!/usr/bin/env python3
"""
Upload cities_landuse data to Vultr Object Storage.

Usage:
    # Set environment variables first
    export S3_ACCESS_KEY="your-access-key"
    export S3_SECRET_KEY="your-secret-key"
    export S3_ENDPOINT="https://ams1.vultrobjects.com"
    export S3_BUCKET="pedestrian-data-prod"

    # Run script
    python scripts/upload_cities_landuse.py
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


def find_landuse_files(directory: str = "data/processed/israel/cities_landuse") -> list[str]:
    """Find all .gpkg files in cities_landuse directory."""
    landuse_dir = Path(directory)
    if not landuse_dir.exists():
        logger.error(f"Directory not found: {directory}")
        return []

    files = sorted(landuse_dir.glob("*.gpkg"))
    return [str(f) for f in files]


def upload_files(storage: VultrStorage, files: list[str], prefix: str) -> tuple[int, int]:
    """
    Upload files to Vultr.

    Args:
        storage: VultrStorage instance
        files: List of local file paths
        prefix: S3 prefix (e.g., "data/processed/israel/cities_landuse")

    Returns:
        Tuple of (successful_count, failed_count)
    """
    success_count = 0
    fail_count = 0

    for file_path in files:
        file_name = os.path.basename(file_path)
        object_key = f"{prefix}/{file_name}"

        # Check file size
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        logger.info(f"Uploading {file_name} ({file_size_mb:.2f} MB)... [{success_count + fail_count + 1}/{len(files)}]")

        # Upload
        if storage.upload_file(file_path, object_key):
            success_count += 1
            logger.info(f"✓ Successfully uploaded: {file_name}")
        else:
            fail_count += 1
            logger.error(f"✗ Failed to upload: {file_name}")

    return success_count, fail_count


def verify_uploads(storage: VultrStorage, prefix: str) -> None:
    """List all files in the prefix to verify uploads."""
    logger.info("\nVerifying uploads...")
    files = storage.list_files(prefix=prefix)

    if not files:
        logger.warning(f"No files found in bucket under '{prefix}' prefix")
        return

    logger.info(f"Found {len(files)} file(s) in Vultr storage:")
    for file_key in files[:10]:  # Show first 10
        logger.info(f"  - {file_key}")
    if len(files) > 10:
        logger.info(f"  ... and {len(files) - 10} more files")


def main():
    parser = argparse.ArgumentParser(description="Upload cities_landuse data to Vultr Object Storage")
    parser.add_argument(
        '--prefix',
        type=str,
        default='data/processed/israel/cities_landuse',
        help='S3 prefix for uploads (default: data/processed/israel/cities_landuse)'
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
        verify_uploads(storage, args.prefix)
        return

    # Find all landuse files
    logger.info("Finding all landuse files in data/processed/israel/cities_landuse/...")
    landuse_files = find_landuse_files()

    if not landuse_files:
        logger.error("No landuse files found in data/processed/israel/cities_landuse/")
        logger.error("Make sure you're running from the project root directory")
        sys.exit(1)

    logger.info(f"Found {len(landuse_files)} landuse file(s) to upload")

    # Calculate total size
    total_size_mb = sum(os.path.getsize(f) for f in landuse_files) / (1024 * 1024)
    logger.info(f"Total size: {total_size_mb:.2f} MB")
    logger.info(f"Upload prefix: {args.prefix}")

    # Confirm upload
    if not args.skip_confirmation:
        response = input("\nProceed with upload? [y/N]: ")
        if response.lower() != 'y':
            logger.info("Upload cancelled")
            return

    # Upload files
    logger.info("\nStarting upload...")
    success, failed = upload_files(storage, landuse_files, args.prefix)

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info(f"Upload complete: {success} succeeded, {failed} failed")
    logger.info("=" * 50)

    # Verify
    verify_uploads(storage, args.prefix)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
