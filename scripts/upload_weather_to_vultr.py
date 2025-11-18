#!/usr/bin/env python3
"""
Upload Israel weather zones GPKG to Vultr Object Storage.
"""
import sys
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    logging.info(f"Loaded environment from {env_path}")

# Add api directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

try:
    from storage_utils import VultrStorage
except ImportError as e:
    print(f"Error: Could not import storage_utils: {e}")
    print("Make sure you're running from the project root and boto3 is installed:")
    print("  pip install boto3")
    sys.exit(1)


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    setup_logging()

    logging.info("=" * 60)
    logging.info("Upload Israel Weather Data to Vultr")
    logging.info("=" * 60)

    # Initialize storage
    storage = VultrStorage()

    # Define file to upload
    local_path = Path("data/processed/israel/israel_weather_zones.gpkg")
    remote_key = "project/data/processed/israel/israel_weather_zones.gpkg"

    if not local_path.exists():
        logging.error(f"File not found: {local_path}")
        return 1

    # Get file size
    file_size_kb = local_path.stat().st_size / 1024
    logging.info(f"File: {local_path}")
    logging.info(f"Size: {file_size_kb:.1f} KB")

    # Upload to Vultr
    logging.info(f"Uploading to Vultr: {remote_key}")
    try:
        success = storage.upload_file(str(local_path), remote_key)

        if not success:
            logging.error("Upload returned False")
            return 1

        logging.info("✓ Upload successful!")

        # Generate presigned URL (temporary public access)
        public_url = storage.generate_presigned_url(remote_key, expires_in=31536000)  # 1 year
        if public_url:
            logging.info(f"Public URL (1 year): {public_url}")

        # Verify upload
        if storage.file_exists(remote_key):
            logging.info("✓ File verified in Vultr storage")
        else:
            logging.error("✗ File verification failed")
            return 1

    except Exception as e:
        logging.error(f"Upload failed: {e}")
        return 1

    logging.info("\n" + "=" * 60)
    logging.info("SUCCESS: Weather data uploaded to Vultr")
    logging.info("=" * 60)
    logging.info("\nNext steps:")
    logging.info("1. The app will automatically download from Vultr in production")
    logging.info("2. Local development will continue using local files")
    logging.info("3. Deploy to Render to use the cloud data")

    return 0


if __name__ == '__main__':
    sys.exit(main())
