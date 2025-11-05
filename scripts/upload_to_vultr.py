#!/usr/bin/env python3
"""
Upload ML models to Vultr Object Storage.

Usage:
    # Set environment variables first
    export S3_ACCESS_KEY="your-access-key"
    export S3_SECRET_KEY="your-secret-key"
    export S3_ENDPOINT="https://ams1.vultrobjects.com"
    export S3_BUCKET="pedestrian-data-prod"

    # Run script
    python scripts/upload_to_vultr.py

    # Or upload specific file
    python scripts/upload_to_vultr.py --file path/to/model.cbm
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


def find_model_files(directory: str = "api/models") -> list[str]:
    """Find all .cbm model files in directory."""
    model_dir = Path(directory)
    if not model_dir.exists():
        logger.error(f"Model directory not found: {directory}")
        return []

    models = list(model_dir.glob("*.cbm"))
    return [str(m) for m in models]


def upload_models(storage: VultrStorage, model_files: list[str]) -> tuple[int, int]:
    """
    Upload model files to Vultr.

    Args:
        storage: VultrStorage instance
        model_files: List of local file paths

    Returns:
        Tuple of (successful_count, failed_count)
    """
    success_count = 0
    fail_count = 0

    for model_path in model_files:
        model_name = os.path.basename(model_path)
        object_key = f"models/{model_name}"

        # Check file size
        file_size_mb = os.path.getsize(model_path) / (1024 * 1024)
        logger.info(f"Uploading {model_name} ({file_size_mb:.2f} MB)...")

        # Upload
        if storage.upload_file(model_path, object_key):
            success_count += 1
            logger.info(f"✓ Successfully uploaded: {model_name}")
        else:
            fail_count += 1
            logger.error(f"✗ Failed to upload: {model_name}")

    return success_count, fail_count


def verify_uploads(storage: VultrStorage) -> None:
    """List all files in the models/ prefix to verify uploads."""
    logger.info("\nVerifying uploads...")
    files = storage.list_files(prefix="models/")

    if not files:
        logger.warning("No files found in bucket under 'models/' prefix")
        return

    logger.info(f"Found {len(files)} file(s) in Vultr storage:")
    for file_key in files:
        logger.info(f"  - {file_key}")


def main():
    parser = argparse.ArgumentParser(description="Upload ML models to Vultr Object Storage")
    parser.add_argument(
        '--file',
        type=str,
        help='Upload specific file (default: all .cbm files in api/models/)'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify existing uploads, do not upload'
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
        verify_uploads(storage)
        return

    # Determine which files to upload
    if args.file:
        if not os.path.exists(args.file):
            logger.error(f"File not found: {args.file}")
            sys.exit(1)
        model_files = [args.file]
    else:
        logger.info("Finding all model files in api/models/...")
        model_files = find_model_files()

        if not model_files:
            logger.error("No model files found in api/models/")
            logger.error("Make sure you're running from the project root directory")
            sys.exit(1)

    logger.info(f"Found {len(model_files)} model file(s) to upload:")
    for model_path in model_files:
        logger.info(f"  - {model_path}")

    # Confirm upload
    total_size_mb = sum(os.path.getsize(f) for f in model_files) / (1024 * 1024)
    logger.info(f"\nTotal size: {total_size_mb:.2f} MB")

    if not args.file:  # Skip confirmation for single file uploads
        response = input("\nProceed with upload? [y/N]: ")
        if response.lower() != 'y':
            logger.info("Upload cancelled")
            return

    # Upload models
    logger.info("\nStarting upload...")
    success, failed = upload_models(storage, model_files)

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info(f"Upload complete: {success} succeeded, {failed} failed")
    logger.info("=" * 50)

    # Verify
    verify_uploads(storage)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
